"""Run the two-minute middle-school invention meeting against live services.

The script creates a fresh room and three fresh members, persists every student
line through AutoUtteranceService, reflects the first four lines for same-meeting
memory, and then runs the constraint-guard, rationale-recall, and 2D-generation
steps. The resulting database rows and LangSmith trace URLs are written to a
capture report.
"""

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("LANGCHAIN_CALLBACKS_BACKGROUND", "false")

from langsmith import Client
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.model.agent import AgentAlert
from app.model.memory import (
    DesignFact,
    DesignFactLink,
    DesignFactUtteranceLink,
    SemanticMemory,
    Topic,
    Utterance,
)
from app.model.room import Room, RoomMember, User
from app.schema.room.request import CreateRoomRequest, EnterRoomRequest
from app.service.agent.reflection_scheduler import ReflectionScheduler
from app.service.room.room_service import RoomService
from app.service.utterance.auto_utterance_service import AutoUtteranceService
from app.service.utterance.topic_routing_service import TopicRoutingService


DEFAULT_OUTPUT_PATH = Path(
    "artifacts/agent-scenarios/middle-school-invention-meeting-live.txt"
)
ROOM_TOPIC = "중학교 1학년 발명품 팀프로젝트: 전기 없는 우산 물기 제거 스탠드"
DEMO_TOPIC_SIMILARITY_THRESHOLD = 0.2
DEMO_LLM_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class ScenarioStep:
    timestamp: str
    name: str
    speaker: str
    utterance: str


INITIAL_STEPS = (
    ScenarioStep(
        timestamp="00:00",
        name="problem_discovery",
        speaker="민준",
        utterance=(
            "비 오는 날 학교 현관에 젖은 우산 때문에 바닥이 미끄러워. "
            "우산 비닐 대신 여러 번 쓸 수 있는 물기 제거기를 만들면 어때?"
        ),
    ),
    ScenarioStep(
        timestamp="00:09",
        name="mechanism_proposal",
        speaker="서연",
        utterance=(
            "접은 우산을 통에 넣고 발판을 밟으면, 안쪽의 세 패드가 모여서 "
            "물기를 닦는 구조로 해보자."
        ),
    ),
    ScenarioStep(
        timestamp="00:18",
        name="explicit_constraints",
        speaker="지우",
        utterance=(
            "제약은 두 가지로 정하자. 모터나 열선 같은 전기 부품은 사용하지 "
            "않고, 재료비는 5만 원 이하로 하자."
        ),
    ),
    ScenarioStep(
        timestamp="00:27",
        name="explicit_rationale",
        speaker="서연",
        utterance=(
            "전기 부품을 빼는 이유는 물이 닿을 때 감전 위험을 줄이고, 우리 힘으로 "
            "쉽게 만들기 위해서야."
        ),
    ),
    ScenarioStep(
        timestamp="00:35",
        name="manual_mechanism_decision",
        speaker="민준",
        utterance=(
            "좋아. 전기 없이 발판이 자전거 브레이크 케이블을 당기는 방식으로 "
            "결정하자."
        ),
    ),
)


REMAINING_STEPS = (
    ScenarioStep(
        timestamp="00:51",
        name="spring_refinement",
        speaker="서연",
        utterance=(
            "패드 뒤에는 스프링을 넣자. 그러면 굵기가 다른 우산도 너무 세게 "
            "눌리지 않을 거야."
        ),
    ),
    ScenarioStep(
        timestamp="00:58",
        name="constraint_violation",
        speaker="민준",
        utterance=(
            "그래도 빨리 말리려면 아래에 작은 모터와 송풍기를 넣는 게 "
            "낫지 않을까?"
        ),
    ),
    ScenarioStep(
        timestamp="01:14",
        name="safe_revision",
        speaker="서연",
        utterance=(
            "맞아. 모터는 빼고, 패드에 세로 홈을 내서 닦은 뒤 공기가 통하게 "
            "하자."
        ),
    ),
    ScenarioStep(
        timestamp="01:22",
        name="rationale_recall",
        speaker="지우",
        utterance="노드베어, 우리가 모터를 쓰지 않기로 한 이유가 정확히 뭐였지?",
    ),
    ScenarioStep(
        timestamp="01:39",
        name="appearance_decision",
        speaker="서연",
        utterance=(
            "겉모양은 둥근 원통으로 하고, 앞에 투명창을 내서 물받이가 찼는지 "
            "볼 수 있게 하자."
        ),
    ),
    ScenarioStep(
        timestamp="01:48",
        name="image_2d_generation",
        speaker="지우",
        utterance=(
            "노드베어, 지금 합의한 둥근 외형과 투명창이 보이도록 2D 콘셉트 "
            "이미지를 만들어줘."
        ),
    ),
)


EXPECTED_GUIDE_TYPES = {
    "constraint_violation": ["CONSTRAINT_VIOLATION"],
    "rationale_recall": ["RATIONALE_RECALL"],
    "image_2d_generation": ["ASSET_GENERATION"],
}


def create_fresh_room() -> tuple[UUID, dict[str, UUID]]:
    service = RoomService()
    db = SessionLocal()
    try:
        created = service.create_room(
            CreateRoomRequest(
                room_topic=ROOM_TOPIC,
                nickname="민준",
            ),
            db,
        )
        room_id = created.room_id
    finally:
        db.close()

    user_ids: dict[str, UUID] = {}
    db = SessionLocal()
    try:
        room = db.scalar(select(Room).where(Room.room_id == room_id))
        if room is None:
            raise RuntimeError("Fresh demo room was not persisted.")
        leader = db.scalar(
            select(User)
            .join(RoomMember, RoomMember.user_id == User.user_id)
            .where(RoomMember.room_id == room_id, User.nickname == "민준")
        )
        if leader is None:
            raise RuntimeError("Fresh demo leader was not persisted.")
        user_ids["민준"] = leader.user_id
    finally:
        db.close()

    for nickname in ("서연", "지우"):
        db = SessionLocal()
        try:
            entered, _reentered = service.enter_room(
                db,
                EnterRoomRequest(room_id=room_id, nickname=nickname),
            )
            user_ids[nickname] = entered.user_id
        finally:
            db.close()

    return room_id, user_ids


async def submit_step(
    *,
    room_id: UUID,
    user_ids: dict[str, UUID],
    step: ScenarioStep,
) -> dict:
    db = SessionLocal()
    try:
        events = await AutoUtteranceService(
            db,
            topic_routing_service=TopicRoutingService(
                similarity_threshold=DEMO_TOPIC_SIMILARITY_THRESHOLD,
            ),
        ).handle_auto_utterance(
            room_id=room_id,
            user_id=user_ids[step.speaker],
            payload={"utterance": step.utterance},
        )
    finally:
        db.close()

    utterance_event = next(
        event for event in events if event.get("event_type") == "UTTERANCE_CREATED"
    )
    guides = [
        event.get("payload", {})
        for event in events
        if event.get("event_type") == "AGENT_GUIDE"
    ]
    return {
        "timestamp": step.timestamp,
        "name": step.name,
        "speaker": step.speaker,
        "utterance": step.utterance,
        "utterance_id": utterance_event["payload"]["utterance_id"],
        "topic_id": utterance_event["payload"]["topic_id"],
        "guides": guides,
    }


def read_persisted_state(room_id: UUID) -> dict:
    db = SessionLocal()
    try:
        utterances = list(
            db.scalars(
                select(Utterance)
                .where(Utterance.room_id == room_id)
                .order_by(Utterance.created_at, Utterance.utterance_id)
            ).all()
        )
        topics = list(
            db.scalars(select(Topic).where(Topic.room_id == room_id)).all()
        )
        facts = list(
            db.scalars(
                select(DesignFact)
                .where(DesignFact.room_id == room_id)
                .order_by(DesignFact.created_at, DesignFact.design_fact_id)
            ).all()
        )
        links = list(
            db.scalars(
                select(DesignFactLink)
                .where(DesignFactLink.room_id == room_id)
                .order_by(DesignFactLink.created_at)
            ).all()
        )
        source_links = list(
            db.scalars(
                select(DesignFactUtteranceLink)
                .join(
                    DesignFact,
                    DesignFact.design_fact_id
                    == DesignFactUtteranceLink.design_fact_id,
                )
                .where(DesignFact.room_id == room_id)
            ).all()
        )
        memories = list(
            db.scalars(
                select(SemanticMemory)
                .where(SemanticMemory.room_id == room_id)
                .order_by(SemanticMemory.created_at)
            ).all()
        )
        alerts = list(
            db.scalars(
                select(AgentAlert)
                .where(AgentAlert.room_id == room_id)
                .order_by(AgentAlert.created_at)
            ).all()
        )
        return {
            "utterance_count": len(utterances),
            "utterances": [
                {
                    "utterance_id": str(item.utterance_id),
                    "topic_id": str(item.topic_id),
                    "state": item.state.value if item.state else None,
                    "text": item.original_text,
                }
                for item in utterances
            ],
            "topic_ids": [str(item.topic_id) for item in topics],
            "facts": [
                {
                    "design_fact_id": str(item.design_fact_id),
                    "fact_type": item.fact_type.value,
                    "status": item.status.value,
                    "content": item.content,
                }
                for item in facts
            ],
            "fact_links": [
                {
                    "from_fact_id": str(item.from_fact_id),
                    "to_fact_id": str(item.to_fact_id),
                    "link_type": item.link_type.value,
                }
                for item in links
            ],
            "source_link_count": len(source_links),
            "memories": [
                {
                    "semantic_memory_id": str(item.semantic_memory_id),
                    "memory_type": item.memory_type.value,
                    "content": item.content,
                }
                for item in memories
            ],
            "alerts": [
                {
                    "agent_alert_id": str(item.agent_alert_id),
                    "triggering_utterance_id": str(item.triggering_utterance_id),
                    "related_fact_id": str(item.related_fact_id),
                    "alert_type": item.alert_type.value,
                    "message": item.message,
                }
                for item in alerts
            ],
        }
    finally:
        db.close()


def required_reflection_facts_present(state: dict) -> bool:
    fact_types = {item["fact_type"] for item in state["facts"]}
    return {"CONSTRAINT", "DECISION", "RATIONALE"}.issubset(fact_types)


async def run_reflection_until_ready(
    *,
    scheduler: ReflectionScheduler,
    room_id: UUID,
    max_attempts: int = 3,
) -> tuple[dict, int]:
    state: dict = {}
    for attempt in range(1, max_attempts + 1):
        await scheduler._run_room(room_id)
        state = await asyncio.to_thread(read_persisted_state, room_id)
        print(
            f"[00:43] reflection attempt={attempt} "
            f"facts={len(state['facts'])} "
            f"links={len(state['fact_links'])} "
            f"memories={len(state['memories'])}"
        )
        if required_reflection_facts_present(state):
            return state, attempt
    return state, max_attempts


def validate_step_guides(step: ScenarioStep, result: dict) -> None:
    expected = EXPECTED_GUIDE_TYPES.get(step.name, [])
    actual = [guide.get("guide_type") for guide in result["guides"]]
    if actual != expected:
        raise RuntimeError(
            f"Unexpected Agent guides for {step.name}: expected={expected}, "
            f"actual={actual}"
        )


async def fetch_langsmith_traces(
    *,
    room_id: UUID,
    started_at: datetime,
) -> list[dict]:
    client = Client()
    expected_names = {"RealtimeUtteranceHotPath", "ReflectionBatchRun"}
    for _attempt in range(5):
        runs = await asyncio.to_thread(
            lambda: list(
                client.list_runs(
                    project_name=settings.LANGSMITH_PROJECT,
                    is_root=True,
                    start_time=started_at - timedelta(seconds=5),
                    limit=100,
                )
            )
        )
        selected = []
        for run in runs:
            metadata = (run.extra or {}).get("metadata", {})
            if (
                run.name in expected_names
                and metadata.get("room_id") == str(room_id)
            ):
                selected.append(
                    {
                        "name": run.name,
                        "run_id": str(run.id),
                        "trace_id": str(run.trace_id),
                        "start_time": run.start_time.isoformat(),
                        "error": run.error,
                        "url": client.get_run_url(
                            run=run,
                            project_name=settings.LANGSMITH_PROJECT,
                        ),
                    }
                )
        if selected:
            return sorted(selected, key=lambda item: item["start_time"])
        await asyncio.sleep(2)
    return []


def build_report(
    *,
    room_id: UUID,
    user_ids: dict[str, UUID],
    started_at: datetime,
    completed_at: datetime,
    steps: list[dict],
    reflection_state: dict,
    final_state: dict,
    traces: list[dict],
) -> str:
    lines = [
        "NodeXR live middle-school invention meeting",
        f"Started at (UTC): {started_at.isoformat()}",
        f"Completed at (UTC): {completed_at.isoformat()}",
        f"LangSmith project: {settings.LANGSMITH_PROJECT}",
        f"Demo topic similarity threshold: {DEMO_TOPIC_SIMILARITY_THRESHOLD}",
        f"Demo Agent LLM timeout seconds: {DEMO_LLM_TIMEOUT_SECONDS}",
        f"Room ID: {room_id}",
        f"Room topic: {ROOM_TOPIC}",
        "Users: "
        + json.dumps(
            {name: str(user_id) for name, user_id in user_ids.items()},
            ensure_ascii=False,
        ),
        "",
        "Scenario steps",
    ]
    for index, step in enumerate(steps, start=1):
        lines.extend(
            [
                f"[{index}] {step['timestamp']} {step['speaker']} / {step['name']}",
                f"Utterance ID: {step['utterance_id']}",
                f"Topic ID: {step['topic_id']}",
                f"Utterance: {step['utterance']}",
                f"AGENT_GUIDE count: {len(step['guides'])}",
            ]
        )
        for guide in step["guides"]:
            lines.extend(
                [
                    f"  Guide type: {guide.get('guide_type')}",
                    f"  Message: {guide.get('message')}",
                    "  Evidence: "
                    + json.dumps(
                        guide.get("evidence", {}),
                        ensure_ascii=False,
                        default=str,
                    ),
                ]
            )
        lines.append("")

    lines.extend(
        [
            "Reflection checkpoint",
            f"Required facts present: {required_reflection_facts_present(reflection_state)}",
            "Facts after checkpoint:",
            json.dumps(reflection_state["facts"], ensure_ascii=False, indent=2),
            "Fact links after checkpoint:",
            json.dumps(reflection_state["fact_links"], ensure_ascii=False, indent=2),
            "Memories after checkpoint:",
            json.dumps(reflection_state["memories"], ensure_ascii=False, indent=2),
            "",
            "Final persisted state",
            f"Utterance count: {final_state['utterance_count']}",
            f"Source link count: {final_state['source_link_count']}",
            "Agent alerts:",
            json.dumps(final_state["alerts"], ensure_ascii=False, indent=2),
            "",
            "LangSmith root traces",
        ]
    )
    if not traces:
        lines.append("No matching traces returned by the LangSmith API query.")
    for trace in traces:
        lines.extend(
            [
                f"Name: {trace['name']}",
                f"Run ID: {trace['run_id']}",
                f"Trace ID: {trace['trace_id']}",
                f"Start: {trace['start_time']}",
                f"Error: {trace['error']}",
                f"URL: {trace['url']}",
                "",
            ]
        )
    return "\n".join(lines)


async def run() -> None:
    engine.echo = False
    settings.AGENT_LLM_TIMEOUT_SECONDS = DEMO_LLM_TIMEOUT_SECONDS
    started_at = datetime.now(timezone.utc)
    room_id, user_ids = await asyncio.to_thread(create_fresh_room)
    results: list[dict] = []

    for step in INITIAL_STEPS:
        result = await submit_step(
            room_id=room_id,
            user_ids=user_ids,
            step=step,
        )
        validate_step_guides(step, result)
        results.append(result)
        print(
            f"[{step.timestamp}] {step.speaker} persisted "
            f"utterance_id={result['utterance_id']} guides={len(result['guides'])}"
        )

    scheduler = ReflectionScheduler()
    reflection_state, reflection_attempts = await run_reflection_until_ready(
        scheduler=scheduler,
        room_id=room_id,
    )

    if not required_reflection_facts_present(reflection_state):
        raise RuntimeError(
            "Reflection did not persist CONSTRAINT, DECISION, and RATIONALE facts; "
            f"room_id={room_id}"
        )
    print(f"[00:43] reflection ready attempts={reflection_attempts}")

    for step in REMAINING_STEPS:
        result = await submit_step(
            room_id=room_id,
            user_ids=user_ids,
            step=step,
        )
        validate_step_guides(step, result)
        results.append(result)
        guide_types = [guide.get("guide_type") for guide in result["guides"]]
        print(
            f"[{step.timestamp}] {step.speaker} persisted "
            f"utterance_id={result['utterance_id']} guides={guide_types}"
        )

    await asyncio.sleep(2)
    final_state = await asyncio.to_thread(read_persisted_state, room_id)
    traces = await fetch_langsmith_traces(
        room_id=room_id,
        started_at=started_at,
    )
    completed_at = datetime.now(timezone.utc)
    report = build_report(
        room_id=room_id,
        user_ids=user_ids,
        started_at=started_at,
        completed_at=completed_at,
        steps=results,
        reflection_state=reflection_state,
        final_state=final_state,
        traces=traces,
    )
    DEFAULT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"Room ID: {room_id}")
    print(f"LangSmith root traces: {len(traces)}")
    print(f"Report: {DEFAULT_OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(run())
