"""15분 회의 시나리오. 발화 적재 / Agent 반응 시점 / 정확도를 기록한다.

정확도를 재려면 정답이 필요하므로 모순과 호출어 명령을 의도적으로 심었다.
- 앞 구간에서 결정/제약을 세우고, 뒤 구간에서 그것을 어기는 발화를 넣는다.
- 모순 발화는 반드시 첫 배치 이후에 나온다. 배치가 fact를 만들기 전에는
  Guard가 볼 것이 없기 때문이다.

설정은 건드리지 않는다. 지금 기본값 그대로의 동작을 기록하는 것이 목적이다.
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")
os.environ.setdefault("LANGCHAIN_CALLBACKS_BACKGROUND", "false")

from langchain_community.callbacks.manager import get_openai_callback
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.model.agent import AgentAlert
from app.model.enum import AlertType
from app.model.memory import (
    DesignFact,
    DesignFactLink,
    DesignFactUtteranceLink,
    SemanticMemory,
    Topic,
    Utterance,
)
from app.model.room import RoomMember, User
from app.schema.room.request import CreateRoomRequest, EnterRoomRequest
from app.service.agent.reflection_scheduler import ReflectionScheduler
from app.service.room.room_service import RoomService
from app.service.utterance.auto_utterance_service import AutoUtteranceService

OUTPUT = Path("artifacts/agent-scenarios/long-meeting-15min.txt")

# gpt-4.1-mini 단가 (USD per 1M tokens)
PRICE_INPUT = 0.40
PRICE_OUTPUT = 1.60
# 예상은 $0.05~0.10이다. 예상의 10배를 넘으면 뭔가 잘못된 것이므로 멈춘다.
COST_CAP_USD = float(os.environ.get("SCENARIO_COST_CAP", "1.00"))

# 모순 경고로 세는 guide_type. enum에서 끌어와 이름 변경을 따라간다.
VIOLATION_GUIDE_TYPES = {
    AlertType.DECISION_CONFLICT.value,
    AlertType.CONSTRAINT_VIOLATION.value,
}
# Recall/생성 guide_type도 스펙 이름을 따른다.
RECALL_GUIDE_TYPES = {
    AlertType.DECISION_RATIONALE_RECALL.value,
    AlertType.CONSTRAINT_RATIONALE_RECALL.value,
    AlertType.CONFLICT_RATIONALE_RECALL.value,
    "ASSET_GENERATION",
}


class CostExceeded(RuntimeError):
    pass


def usd(tracker) -> float:
    return (
        tracker.prompt_tokens / 1_000_000 * PRICE_INPUT
        + tracker.completion_tokens / 1_000_000 * PRICE_OUTPUT
    )


@dataclass
class Line:
    at: str                      # 회의 경과 시각
    speaker: str
    text: str
    topic: str                   # 정답 topic
    move: str                    # 정답 dialogue_move
    guard_expected: bool = False # Guard 경고가 떠야 하는 발화인가
    violates: str = ""           # 무엇을 위반하는가 (경고 근거)
    command: str = ""            # 호출어 명령의 정답 (없으면 빈 문자열)
    note: str = ""


# ── 0:00 ~ 5:00  전원 방식 ────────────────────────────────────────────────
BLOCK_1 = [
    Line("0:10", "민준", "이번 동아리 프로젝트는 학교 텃밭에 자동으로 물 주는 장치를 만드는 거야.", "전원", "PROPOSE"),
    Line("0:25", "서연", "좋다. 근데 텃밭에 콘센트가 하나도 없어.", "전원", "INFORM"),
    Line("0:40", "지우", "그러면 전기를 어디서 끌어오지?", "전원", "ASK"),
    Line("0:55", "민준", "태양광 패널을 쓰면 되지 않을까?", "전원", "PROPOSE"),
    Line("1:10", "서연", "오 그거 괜찮은데.", "전원", "AGREE"),
    Line("1:30", "지우", "태양광은 흐린 날에 안 돌아갈 텐데.", "전원", "DISAGREE"),
    Line("1:50", "민준", "작은 보조 배터리를 같이 달면 흐린 날도 버틸 수 있어.", "전원", "PROPOSE"),
    Line("2:10", "서연", "그럼 태양광 패널하고 보조 배터리로만 전원을 쓰고 콘센트는 안 쓰는 걸로 정하자.", "전원", "DECIDE",
         note="핵심 결정 1 — 이후 모순의 기준"),
    Line("2:30", "지우", "응 그렇게 하자.", "전원", "AGREE"),
    Line("2:50", "민준", "동아리 지원금이 오만 원이라서 전체 예산은 오만 원을 넘기면 안 돼.", "전원", "DECIDE",
         note="핵심 제약 1 — 이후 모순의 기준"),
    Line("3:10", "서연", "알겠어. 그 안에서 맞춰보자.", "전원", "AGREE"),
    Line("3:30", "지우", "태양광 패널은 얼마쯤 해?", "전원", "ASK"),
    Line("3:50", "민준", "작은 건 만오천 원쯤 하더라.", "전원", "INFORM"),
    Line("4:10", "서연", "그럼 패널은 화단 울타리 위에 고정하자.", "전원", "PROPOSE"),
    Line("4:30", "지우", "거기가 하루 종일 해가 잘 들어.", "전원", "INFORM"),
]

# ── 5:00 ~ 10:00  물 공급 방식 ────────────────────────────────────────────
BLOCK_2 = [
    Line("5:10", "민준", "이제 물을 어떻게 보낼지 정하자.", "물공급", "PROPOSE"),
    Line("5:30", "서연", "전동 펌프를 쓰면 확실하게 물이 나갈 거야.", "물공급", "PROPOSE"),
    Line("5:50", "지우", "펌프는 전기를 많이 먹어서 태양광으로는 부족할 것 같아.", "물공급", "DISAGREE"),
    Line("6:10", "민준", "물탱크를 높은 곳에 두고 중력으로 흘려보내면 전기가 거의 안 들어.", "물공급", "PROPOSE"),
    Line("6:30", "서연", "근데 중력식은 물이 천천히 나가잖아.", "물공급", "DISAGREE"),
    Line("6:50", "지우", "텃밭은 천천히 줘도 괜찮아. 오히려 흙에 더 잘 스며들어.", "물공급", "INFORM"),
    Line("7:10", "민준", "그리고 밸브만 여닫으면 되니까 전기는 밸브에만 쓰면 돼.", "물공급", "INFORM"),
    Line("7:30", "서연", "듣고 보니 그게 낫겠다.", "물공급", "AGREE"),
    Line("7:50", "지우", "그럼 중력식 물탱크로 정하자.", "물공급", "DECIDE",
         note="핵심 결정 2"),
    Line("8:10", "민준", "물탱크는 이십 리터짜리로 하자.", "물공급", "PROPOSE"),
    Line("8:30", "서연", "그 정도면 일주일은 버티겠다.", "물공급", "AGREE"),
    Line("8:50", "지우", "탱크는 창고 지붕 위에 올리면 높이가 충분해.", "물공급", "PROPOSE"),
    Line("9:10", "민준", "좋아 그렇게 하자.", "물공급", "AGREE"),
    Line("9:30", "서연", "이거 언제까지 만들어야 하지?", "물공급", "ASK",
         note="호출어 없는 질문 — Recall이 돌면 안 된다"),
]

# ── 10:00 ~ 15:00  센서와 마무리 (여기서 모순을 심는다) ────────────────────
BLOCK_3 = [
    Line("10:10", "지우", "흙이 마른 걸 어떻게 알지?", "센서", "ASK"),
    Line("10:30", "민준", "토양 수분 센서를 꽂아두면 돼.", "센서", "PROPOSE"),
    Line("10:50", "서연", "센서 값을 읽으려면 전기가 꾸준히 필요할 텐데, 그냥 교실 콘센트에서 전선을 끌어오자.",
         "센서", "PROPOSE", guard_expected=True, violates="콘센트를 쓰지 않기로 한 결정",
         note="모순 1 — 결정 위반"),
    Line("11:15", "지우", "노드베어, 우리가 콘센트를 안 쓰기로 한 이유가 뭐였지?", "센서", "ASK",
         command="RATIONALE_RECALL"),
    Line("11:40", "민준", "아 맞다. 텃밭에 콘센트가 없어서였지.", "센서", "INFORM"),
    Line("12:00", "서연", "그럼 센서도 태양광 쪽에 물리자.", "센서", "PROPOSE"),
    Line("12:20", "지우", "센서는 정밀한 게 좋으니까 팔만 원짜리 고급형으로 하자.", "센서", "PROPOSE",
         guard_expected=True, violates="예산 오만 원 제약",
         note="모순 2 — 제약 위반"),
    Line("12:45", "민준", "그건 예산을 넘어. 만 원대 기본형으로 하자.", "센서", "DECIDE"),
    Line("13:05", "서연", "노드베어, 물탱크 방식 정할 때 반대 의견이 뭐였어?", "센서", "ASK",
         command="CONFLICT_RECALL"),
    Line("13:30", "지우", "맞아 그런 얘기가 있었지.", "센서", "AGREE"),
    Line("13:50", "민준", "센서는 고랑마다 하나씩 해서 세 개 꽂자.", "센서", "PROPOSE"),
    Line("14:10", "서연", "좋아 그렇게 정리하자.", "센서", "AGREE"),
    Line("14:30", "지우", "노드베어, 지금까지 정한 내용으로 2D 콘셉트 이미지 만들어줘.", "센서", "ASK",
         command="GENERATE_2D"),
    Line("14:50", "민준", "오늘은 여기까지 하자.", "센서", "OTHER"),
]

BLOCKS = [("1차 (0:00~5:00)", BLOCK_1), ("2차 (5:00~10:00)", BLOCK_2), ("3차 (10:00~15:00)", BLOCK_3)]
ALL_LINES = [line for _name, block in BLOCKS for line in block]


def create_room() -> tuple[UUID, dict[str, UUID]]:
    service = RoomService()
    db = SessionLocal()
    try:
        created = service.create_room(
            CreateRoomRequest(
                room_name=f"long-meeting-{datetime.now(timezone.utc):%m%d-%H%M%S}",
                room_topic="학교 텃밭 자동 물주기 장치",
                nickname="민준",
            ),
            db,
        )
        room_id = created.room_id
    finally:
        db.close()

    ids: dict[str, UUID] = {}
    db = SessionLocal()
    try:
        leader = db.scalar(
            select(User)
            .join(RoomMember, RoomMember.user_id == User.user_id)
            .where(RoomMember.room_id == room_id, User.nickname == "민준")
        )
        ids["민준"] = leader.user_id
    finally:
        db.close()

    for nickname in ("서연", "지우"):
        db = SessionLocal()
        try:
            entered, _ = service.enter_room(
                db, EnterRoomRequest(room_id=room_id, nickname=nickname)
            )
            ids[nickname] = entered.user_id
        finally:
            db.close()
    return room_id, ids


async def submit(room_id: UUID, ids: dict[str, UUID], line: Line) -> dict:
    started = time.perf_counter()
    db = SessionLocal()
    try:
        events = await AutoUtteranceService(db).handle_auto_utterance(
            room_id=room_id,
            user_id=ids[line.speaker],
            payload={"utterance": line.text},
        )
    finally:
        db.close()
    elapsed_ms = (time.perf_counter() - started) * 1000

    created = next(e for e in events if e.get("event_type") == "UTTERANCE_CREATED")
    guides = [
        e.get("payload", {}) for e in events if e.get("event_type") == "AGENT_GUIDE"
    ]
    return {
        "utterance_id": created["payload"]["utterance_id"],
        "topic_id": created["payload"]["topic_id"],
        "guides": guides,
        "elapsed_ms": elapsed_ms,
    }


def read_state(room_id: UUID) -> dict:
    db = SessionLocal()
    try:
        utterances = list(db.scalars(
            select(Utterance).where(Utterance.room_id == room_id)
            .order_by(Utterance.created_at, Utterance.utterance_id)).all())
        topics = list(db.scalars(
            select(Topic).where(Topic.room_id == room_id)
            .order_by(Topic.created_at)).all())
        facts = list(db.scalars(
            select(DesignFact).where(DesignFact.room_id == room_id)
            .order_by(DesignFact.created_at)).all())
        links = list(db.scalars(
            select(DesignFactLink).where(DesignFactLink.room_id == room_id)).all())
        source_links = list(db.scalars(
            select(DesignFactUtteranceLink)
            .join(DesignFact,
                  DesignFact.design_fact_id == DesignFactUtteranceLink.design_fact_id)
            .where(DesignFact.room_id == room_id)).all())
        memories = list(db.scalars(
            select(SemanticMemory).where(SemanticMemory.room_id == room_id)
            .order_by(SemanticMemory.created_at)).all())
        alerts = list(db.scalars(
            select(AgentAlert).where(AgentAlert.room_id == room_id)
            .order_by(AgentAlert.created_at)).all())
        fact_by_id = {f.design_fact_id: f for f in facts}
        return {
            "utterances": [
                {"id": str(u.utterance_id), "topic_id": str(u.topic_id),
                 "state": u.state.value if u.state else None, "text": u.original_text}
                for u in utterances],
            "topics": [{"id": str(t.topic_id), "summary": t.summary} for t in topics],
            "facts": [
                {"id": str(f.design_fact_id), "topic_id": str(f.topic_id),
                 "type": f.fact_type.value, "status": f.status.value,
                 "content": f.content}
                for f in facts],
            "links": [
                {"from": fact_by_id[l.from_fact_id].content if l.from_fact_id in fact_by_id else "?",
                 "type": l.link_type.value,
                 "to": fact_by_id[l.to_fact_id].content if l.to_fact_id in fact_by_id else "?"}
                for l in links],
            "source_link_count": len(source_links),
            "memories": [
                {"type": m.memory_type.value, "topic_id": str(m.topic_id),
                 "content": m.content}
                for m in memories],
            "alerts": [
                {"type": a.alert_type.value, "utterance_id": str(a.triggering_utterance_id),
                 "related_fact": fact_by_id[a.related_fact_id].content
                 if a.related_fact_id in fact_by_id else "?",
                 "message": a.message}
                for a in alerts],
        }
    finally:
        db.close()


def pairwise_f1(truth: list[str], predicted: list[str]) -> dict:
    tp = fp = fn = 0
    for i, j in combinations(range(len(truth)), 2):
        st, sp = truth[i] == truth[j], predicted[i] == predicted[j]
        if st and sp:
            tp += 1
        elif not st and sp:
            fp += 1
        elif st and not sp:
            fn += 1
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    pairs = list(combinations(range(len(truth)), 2))
    base = sum(1 for i, j in pairs if truth[i] == truth[j]) / len(pairs)
    return {"f1": 2 * p * r / (p + r) if (p + r) else 0.0,
            "precision": p, "recall": r, "base_rate": base}


async def main() -> None:
    with get_openai_callback() as tracker:
        await run_meeting(tracker)


async def run_meeting(tracker) -> None:
    room_id, ids = create_room()
    scheduler = ReflectionScheduler()
    print(f"room_id={room_id}\n")

    timeline: list[dict] = []
    batch_reports: list[dict] = []

    for block_name, block in BLOCKS:
        print(f"── {block_name} " + "─" * 50)
        for line in block:
            result = await submit(room_id, ids, line)
            guide_types = [g.get("guide_type") for g in result["guides"]]
            timeline.append({
                "at": line.at, "speaker": line.speaker, "text": line.text,
                "topic_truth": line.topic, "move_truth": line.move,
                "guard_expected": line.guard_expected, "violates": line.violates,
                "command_truth": line.command, "note": line.note,
                "utterance_id": result["utterance_id"],
                "topic_id": result["topic_id"],
                "guides": guide_types,
                "guide_messages": [g.get("message", "") for g in result["guides"]],
                "elapsed_ms": result["elapsed_ms"],
            })
            mark = "  "
            if guide_types:
                mark = "▶ "
            print(f"{mark}[{line.at}] {line.speaker}: {line.text[:42]}"
                  f"{'…' if len(line.text) > 42 else ''}")
            if guide_types:
                for g in result["guides"]:
                    print(f"      └ AGENT_GUIDE {g.get('guide_type')}: "
                          f"{g.get('message', '')[:70]}")

        spent = usd(tracker)
        print(f"\n   … 배치 실행 …   (누적 ${spent:.4f})")
        if spent > COST_CAP_USD:
            raise CostExceeded(f"상한 ${COST_CAP_USD} 초과: ${spent:.4f}")
        await scheduler._run_room(room_id)
        state = read_state(room_id)
        batch_reports.append({"block": block_name, "state": state})
        print(f"   topic={len(state['topics'])} fact={len(state['facts'])} "
              f"link={len(state['links'])} memory={len(state['memories'])} "
              f"alert={len(state['alerts'])}\n")

    final = read_state(room_id)
    cost = {
        "input_tokens": tracker.prompt_tokens,
        "output_tokens": tracker.completion_tokens,
        "llm_calls": tracker.successful_requests,
        "usd": usd(tracker),
    }
    report = build_report(room_id, timeline, batch_reports, final, cost)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(report, encoding="utf-8")
    print(report[report.index("정확도"):])
    print(f"\n보고서: {OUTPUT}")


def build_report(room_id, timeline, batch_reports, final, cost) -> str:
    out: list[str] = []
    w = out.append

    w("=" * 78)
    w("15분 회의 시나리오 기록")
    w("=" * 78)
    w(f"room_id={room_id}")
    w(f"실행 시각: {datetime.now(timezone.utc).isoformat()}")
    w("")
    w("설정 (변경 없이 현재 기본값)")
    for key in ("TOPIC_SIMILARITY_THRESHOLD", "TOPIC_ROUTING_MODE",
                "AGENT_GUARD_GATING_MODE", "AGENT_WAKE_WORD_REQUIRED",
                "BATCH_TOPIC_RESEGMENT_ENABLED", "AGENT_RETRIEVAL_FALLBACK_ENABLED",
                "MEMORY_GUARD_ALERT_THRESHOLD", "NOISE_FILTER_MODE"):
        w(f"  {key} = {getattr(settings, key)}")
    w("")

    w("=" * 78)
    w("1. 타임라인 — 발화와 Agent 반응")
    w("=" * 78)
    for item in timeline:
        flag = "▶" if item["guides"] else " "
        w(f"{flag} [{item['at']}] {item['speaker']}: {item['text']}")
        w(f"     topic={item['topic_id'][:8]} ({item['topic_truth']}) "
          f"| {item['elapsed_ms']:.0f}ms")
        if item["note"]:
            w(f"     * {item['note']}")
        for guide_type, message in zip(item["guides"], item["guide_messages"]):
            w(f"     └ AGENT_GUIDE {guide_type}")
            w(f"       {message}")
    w("")

    w("=" * 78)
    w("2. 배치별 DB 적재")
    w("=" * 78)
    for report in batch_reports:
        s = report["state"]
        w(f"\n── {report['block']} 이후")
        w(f"   utterance={len(s['utterances'])}  topic={len(s['topics'])}  "
          f"fact={len(s['facts'])}  link={len(s['links'])}  "
          f"memory={len(s['memories'])}  alert={len(s['alerts'])}")
    w("")

    w("=" * 78)
    w("3. 최종 DB 상태")
    w("=" * 78)
    states: dict[str, int] = {}
    for u in final["utterances"]:
        states[u["state"]] = states.get(u["state"], 0) + 1
    w(f"\nutterances ({len(final['utterances'])}건) state 분포: {states}")
    w(f"\ntopics ({len(final['topics'])}개)")
    for t in final["topics"]:
        count = sum(1 for u in final["utterances"] if u["topic_id"] == t["id"])
        w(f"  {t['id'][:8]}  발화 {count}건  요약: {t['summary']}")
    w(f"\ndesign_facts ({len(final['facts'])}건)")
    by_type: dict[str, int] = {}
    for f in final["facts"]:
        by_type[f["type"]] = by_type.get(f["type"], 0) + 1
        w(f"  [{f['type']:16s}] {f['content']}")
    w(f"\n  타입 분포: {by_type}")
    w(f"\ndesign_fact_links ({len(final['links'])}건)")
    for l in final["links"]:
        w(f"  {l['from'][:34]} --{l['type']}--> {l['to'][:34]}")
    w(f"\ndesign_fact_utterance_links: {final['source_link_count']}건")
    w(f"\nsemantic_memories ({len(final['memories'])}건)")
    for m in final["memories"]:
        w(f"  [{m['type']}] {m['content']}")
    w(f"\nagent_alerts ({len(final['alerts'])}건)")
    for a in final["alerts"]:
        w(f"  [{a['type']}] 근거fact: {a['related_fact']}")
        w(f"    {a['message']}")
    w("")

    w("=" * 78)
    w("4. 정확도")
    w("=" * 78)

    # (1) topic 분류
    truth = [i["topic_truth"] for i in timeline]
    predicted = [i["topic_id"] for i in timeline]
    topic_score = pairwise_f1(truth, predicted)
    w(f"\n[topic 분류]  정답 {len(set(truth))}개 → 실제 {len(set(predicted))}개")
    w(f"  pairwise F1 = {topic_score['f1']:.3f}")
    w(f"  정밀도 = {topic_score['precision']:.3f}  (기저율 {topic_score['base_rate']:.3f})")
    w(f"  재현율 = {topic_score['recall']:.3f}")

    # (2) Guard 경고
    expected_guard = [i for i in timeline if i["guard_expected"]]
    got_alert = [
        i for i in timeline
        if any(g in VIOLATION_GUIDE_TYPES for g in i["guides"])
    ]
    tp = [i for i in expected_guard if i in got_alert]
    fp = [i for i in got_alert if not i["guard_expected"]]
    fn = [i for i in expected_guard if i not in got_alert]
    precision = len(tp) / len(got_alert) if got_alert else 0.0
    recall = len(tp) / len(expected_guard) if expected_guard else 0.0
    w(f"\n[모순 탐지]  심어둔 모순 {len(expected_guard)}건")
    w(f"  탐지 {len(tp)}건 / 오탐 {len(fp)}건 / 미탐 {len(fn)}건")
    w(f"  정밀도 = {precision:.3f}  재현율 = {recall:.3f}")
    for i in tp:
        w(f"  ⭕ 탐지: [{i['at']}] {i['text'][:46]} ({i['violates']})")
    for i in fn:
        w(f"  ❌ 미탐: [{i['at']}] {i['text'][:46]} ({i['violates']})")
    for i in fp:
        w(f"  ⚠️ 오탐: [{i['at']}] {i['text'][:46]}")

    # (3) 호출어 명령 분류
    commands = [i for i in timeline if i["command_truth"]]
    guide_for_command = {
        "RATIONALE_RECALL": {
            AlertType.DECISION_RATIONALE_RECALL.value,
            AlertType.CONSTRAINT_RATIONALE_RECALL.value,
        },
        "CONFLICT_RECALL": {AlertType.CONFLICT_RATIONALE_RECALL.value},
        "GENERATE_2D": {"ASSET_GENERATION"},
    }
    hit = 0
    w(f"\n[호출어 명령 분류]  {len(commands)}건")
    for i in commands:
        want = guide_for_command[i["command_truth"]]
        ok = bool(want.intersection(i["guides"]))
        hit += 1 if ok else 0
        w(f"  {'⭕' if ok else '❌'} [{i['at']}] 기대={i['command_truth']} "
          f"→ 실제 guide={i['guides']}")
        w(f"      {i['text']}")
    w(f"  정확도 = {hit}/{len(commands)} = {hit / len(commands):.3f}"
      if commands else "  (없음)")

    # (4) 호출어 없는 발화에서 Recall/생성이 돌지 않았는가
    leaked = [
        i for i in timeline
        if not i["command_truth"]
        and any(g in RECALL_GUIDE_TYPES for g in i["guides"])
    ]
    non_command = [i for i in timeline if not i["command_truth"]]
    w(f"\n[호출어 게이팅]  호출어 없는 발화 {len(non_command)}건 중 "
      f"Recall/생성 오작동 {len(leaked)}건")
    for i in leaked:
        w(f"  ⚠️ [{i['at']}] {i['text'][:46]} → {i['guides']}")
    w(f"  정확도 = {(len(non_command) - len(leaked)) / len(non_command):.3f}")

    # (5) 핵심 설계 내용이 fact로 잡혔는가
    key_points = [
        ("콘센트를 쓰지 않는다", ["콘센트", "태양광"]),
        ("예산 오만 원 이하", ["오만", "5만", "예산"]),
        ("중력식 물탱크", ["중력", "물탱크"]),
        ("토양 수분 센서", ["센서"]),
    ]
    fact_text = " ".join(f["content"] for f in final["facts"])
    captured = [(name, any(k in fact_text for k in keys)) for name, keys in key_points]
    w(f"\n[핵심 설계 내용 추출]  {sum(1 for _n, ok in captured if ok)}/{len(captured)}")
    for name, ok in captured:
        w(f"  {'⭕' if ok else '❌'} {name}")

    # (6) 발화 저장
    wake_lines = [i for i in timeline if i["command_truth"]]
    skip_count = sum(1 for u in final["utterances"] if u["state"] == "SKIP")
    w(f"\n[발화 저장]  전체 {len(final['utterances'])}건")
    w(f"  호출어 발화 {len(wake_lines)}건 → SKIP 저장 {skip_count}건 "
      f"({'일치' if skip_count == len(wake_lines) else '불일치'})")
    w(f"  state 분포: {states}")

    # (7) 지연
    latencies = sorted(i["elapsed_ms"] for i in timeline)
    n = len(latencies)
    w(f"\n[발화 처리 지연]  {n}건")
    w(f"  중앙값 {latencies[n // 2]:.0f}ms  "
      f"p90 {latencies[int(n * 0.9)]:.0f}ms  최대 {latencies[-1]:.0f}ms")
    guided = [i["elapsed_ms"] for i in timeline if i["guides"]]
    plain = [i["elapsed_ms"] for i in timeline if not i["guides"]]
    if guided:
        w(f"  Agent 응답 있음 {len(guided)}건 평균 {sum(guided) / len(guided):.0f}ms")
    if plain:
        w(f"  Agent 응답 없음 {len(plain)}건 평균 {sum(plain) / len(plain):.0f}ms")

    w(f"\n[LLM 비용]  gpt-4.1-mini")
    w(f"  호출 {cost['llm_calls']}건")
    w(f"  input {cost['input_tokens']:,} tokens / output {cost['output_tokens']:,} tokens")
    w(f"  = ${cost['usd']:.4f}  (발화 1건당 ${cost['usd'] / len(timeline):.5f})")

    return "\n".join(out)


asyncio.run(main())
