"""Run a live realtime-Agent scenario against the seeded dummy meeting room.

The scenario uses the existing ``AutoUtteranceService`` so each step follows the
same persistence, topic-routing, Agent, and AGENT_GUIDE construction path used
by ``UTTERANCE_CREATE``. It intentionally writes the submitted test utterances
and any generated agent alerts to the configured database.
"""

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("LANGCHAIN_CALLBACKS_BACKGROUND", "false")

from app.db.session import SessionLocal
from app.model.enum import RoomMemberState
from app.repository.room_repository import RoomRepository
from app.service.utterance.auto_utterance_service import AutoUtteranceService


DUMMY_ROOM_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
DUMMY_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
DEFAULT_OUTPUT_PATH = Path("artifacts/agent-scenarios/dummy-agent-meeting.txt")


@dataclass(frozen=True)
class ScenarioStep:
    name: str
    purpose: str
    utterance: str


SCENARIO = (
    ScenarioStep(
        name="safety_constraint_conflict",
        purpose="기존의 둥글고 부드러운 집게 팔 안전 제약 위반 감지",
        utterance="집게 팔 끝을 뾰족한 금속 못으로 바꾸자.",
    ),
    ScenarioStep(
        name="poster_rationale_recall",
        purpose="바다 보호 포스터 배경 결정의 근거 회상",
        utterance="발표 포스터 배경에 물고기와 파도를 넣기로 한 이유를 알려줘.",
    ),
    ScenarioStep(
        name="conflict_recall_without_stored_conflict",
        purpose="저장된 갈등 근거가 없을 때의 안전한 응답 확인",
        utterance="집게 팔 모양을 두고 전에 반대한 의견이 뭐였지?",
    ),
    ScenarioStep(
        name="ordinary_discussion",
        purpose="일반 발화에서 불필요한 Agent guide 억제 확인",
        utterance="분리수거 통의 두 칸에 붙일 이름표 문구를 같이 정해 보자.",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"text report path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--steps",
        nargs="+",
        choices=[step.name for step in SCENARIO],
        help="run only the named scenario steps",
    )
    return parser.parse_args()


def validate_dummy_room() -> None:
    db = SessionLocal()
    try:
        repository = RoomRepository()
        room = repository.find_room_by_id(db, DUMMY_ROOM_ID)
        if room is None or not room.is_active:
            raise RuntimeError(
                "Seeded active dummy room was not found. Load seed_all_dummy.sql first."
            )
        member = repository.find_joined_member_by_user_id(
            db,
            room_id=DUMMY_ROOM_ID,
            user_id=DUMMY_USER_ID,
        )
        if member is None or member.state != RoomMemberState.JOINED:
            raise RuntimeError(
                "Seeded dummy user is not a joined member of the dummy room."
            )
    finally:
        db.close()


async def run_scenario(
    steps: tuple[ScenarioStep, ...],
) -> list[tuple[ScenarioStep, list[dict]]]:
    results: list[tuple[ScenarioStep, list[dict]]] = []
    for step in steps:
        db = SessionLocal()
        try:
            service = AutoUtteranceService(db)
            events = await service.handle_auto_utterance(
                room_id=DUMMY_ROOM_ID,
                user_id=DUMMY_USER_ID,
                payload={"utterance": step.utterance},
            )
            results.append((step, events))
        finally:
            db.close()
    return results


def guide_events(events: list[dict]) -> list[dict]:
    return [event for event in events if event.get("event_type") == "AGENT_GUIDE"]


def build_report(results: list[tuple[ScenarioStep, list[dict]]]) -> str:
    lines = [
        "NodeXR dummy realtime-Agent meeting scenario",
        f"Generated at (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"Room ID: {DUMMY_ROOM_ID}",
        "Room topic: 초등학생 만들기 팀프로젝트: 바닷속 쓰레기를 줍는 친환경 청소 로봇",
        "",
    ]

    for index, (step, events) in enumerate(results, start=1):
        guides = guide_events(events)
        utterance_event = next(
            (event for event in events if event.get("event_type") == "UTTERANCE_CREATED"),
            None,
        )
        lines.extend(
            [
                f"[{index}] {step.name}",
                f"Purpose: {step.purpose}",
                f"Utterance: {step.utterance}",
                "Persisted utterance: "
                + json.dumps(
                    utterance_event.get("payload", {}) if utterance_event else {},
                    ensure_ascii=False,
                    default=str,
                ),
                f"AGENT_GUIDE count: {len(guides)}",
            ]
        )
        if not guides:
            lines.append("AGENT_GUIDE: none")
        for guide_index, guide in enumerate(guides, start=1):
            payload = guide.get("payload", {})
            lines.extend(
                [
                    f"  Guide {guide_index} type: {payload.get('guide_type')}",
                    f"  Message: {payload.get('message')}",
                    "  Evidence: "
                    + json.dumps(
                        payload.get("evidence", {}),
                        ensure_ascii=False,
                        default=str,
                    ),
                ]
            )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    selected_steps = (
        tuple(step for step in SCENARIO if step.name in set(args.steps))
        if args.steps
        else SCENARIO
    )
    validate_dummy_room()
    results = asyncio.run(run_scenario(selected_steps))
    report = build_report(results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote Agent scenario report to {args.output}")


if __name__ == "__main__":
    main()
