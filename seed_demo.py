"""시연용 과거 회의 상태를 DB에 심는다.

사용법:
    docker compose cp seed_demo.py backend:/app/seed_demo.py
    docker compose exec backend python /app/seed_demo.py <room_id>

이미 심은 방에 다시 돌리면 기존 시드를 지우고 새로 넣는다(멱등).
"""

import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, delete

from app.db.session import SessionLocal
from app.model.enum import (
    DesignFactLinkType,
    DesignFactStatus,
    DesignFactType,
    DesignFactUtteranceLinkRole,
    MemoryStatus,
    SemanticMemoryType,
    TopicStatus,
    UtteranceState,
)
from app.model.agent import AgentAlert
from app.model.memory import (
    DesignFact,
    DesignFactLink,
    DesignFactUtteranceLink,
    NodeUtteranceLink,
    SemanticMemory,
    Topic,
    Utterance,
    UtteranceAnnotation,
)
from app.model.room import Room, RoomMember
from app.service.utterance.embedding_service import EmbeddingService

SEED_MARK = "[demo-seed]"

# ── 과거 발화 대본 ────────────────────────────────────────────
# (화자 순번, 본문) — 화자 순번은 방 참여자 목록에 순서대로 매핑한다.
PAST_UTTERANCES = [
    (0, "길에 떨어진 쓰레기를 주워 담는 로봇을 만들자."),
    (1, "사람 다니는 보도로 같이 다녀야 하는데."),
    (0, "폭은 60센티를 넘지 말자."),
    (1, "밖에 계속 있으면 비도 맞을 텐데."),
    (0, "전기 부품은 밖으로 드러내지 말자. 비 맞으면 위험해."),
    (1, "쓰레기는 집게로 집을까?"),
    (0, "집게는 하나씩 집어서 너무 느려."),
    (1, "그럼 빗자루처럼 쓸어 담는 브러시는 어때?"),
    (0, "브러시로 하자. 낙엽까지 쓸어 담을 수 있어."),
    (1, "겉은 뭘로 만들까?"),
    (0, "재활용 플라스틱으로 하자. 가볍고 주제에도 맞아."),
    (1, "좋아. 브러시랑 수거통까지 정해졌네."),
]

# ── 설계 사실 ────────────────────────────────────────────────
# key: (타입, 상태, 내용, 근거가 된 과거 발화 인덱스들)
FACTS = {
    "c_width": (
        DesignFactType.CONSTRAINT,
        DesignFactStatus.CONFIRMED,
        "로봇 폭은 60cm를 넘지 않는다. 보도로 다니기 때문이다.",
        [1, 2],
    ),
    "c_electric": (
        DesignFactType.CONSTRAINT,
        DesignFactStatus.CONFIRMED,
        "전기 부품을 밖으로 드러내지 않는다. 비를 맞기 때문이다.",
        [3, 4],
    ),
    "d_brush": (
        DesignFactType.DECISION,
        DesignFactStatus.CONFIRMED,
        "쓰레기는 브러시로 쓸어 담는다.",
        [7, 8],
    ),
    "d_material": (
        DesignFactType.DECISION,
        DesignFactStatus.CONFIRMED,
        "겉은 재활용 플라스틱으로 만든다.",
        [10],
    ),
    "p_gripper": (
        DesignFactType.PROPOSAL,
        DesignFactStatus.REJECTED,
        "집게로 쓰레기를 집자.",
        [5],
    ),
    "a_gripper_slow": (
        DesignFactType.ARGUMENT_AGAINST,
        DesignFactStatus.ACTIVE,
        "집게는 하나씩 집어서 느리다.",
        [6],
    ),
    "r_brush": (
        DesignFactType.RATIONALE,
        DesignFactStatus.ACTIVE,
        "브러시로 정한 이유는 낙엽처럼 작은 쓰레기까지 쓸어 담을 수 있어서다.",
        [8],
    ),
    "r_material": (
        DesignFactType.RATIONALE,
        DesignFactStatus.ACTIVE,
        "재활용 플라스틱으로 정한 이유는 가볍고 환경 로봇 주제에 맞아서다.",
        [10],
    ),
}

# (from, to, 관계)
FACT_LINKS = [
    ("r_brush", "d_brush", DesignFactLinkType.RATIONALE_OF),
    ("r_material", "d_material", DesignFactLinkType.RATIONALE_OF),
    ("a_gripper_slow", "p_gripper", DesignFactLinkType.OPPOSES),
    ("d_brush", "p_gripper", DesignFactLinkType.RESOLVES),
    ("c_width", "d_brush", DesignFactLinkType.CONSTRAINS),
    ("c_electric", "d_brush", DesignFactLinkType.CONSTRAINS),
]

# 의미 기억(근거 복기가 함께 훑는다)
MEMORIES = [
    (SemanticMemoryType.CONSTRAINT, "폭 60cm 이하 — 보도로 다니니까."),
    (SemanticMemoryType.CONSTRAINT, "전기 부품 노출 금지 — 비를 맞으니까."),
    (SemanticMemoryType.DECISION, "쓰레기는 브러시로 쓸어 담는다."),
    (SemanticMemoryType.DECISION, "겉은 재활용 플라스틱."),
    (SemanticMemoryType.RATIONALE, "브러시로 정한 이유는 작은 쓰레기까지 담기 위해서."),
    (SemanticMemoryType.RATIONALE, "재활용 플라스틱으로 정한 이유는 가볍고 주제에 맞아서."),
    (SemanticMemoryType.CONFLICT, "집게는 정확하지만 느려서 안 쓰기로 했다."),
]


def main(room_id: uuid.UUID) -> None:
    db = SessionLocal()
    embedder = EmbeddingService()
    try:
        room = db.get(Room, room_id)
        if room is None:
            raise SystemExit(f"방을 찾을 수 없다: {room_id}")

        members = db.scalars(
            select(RoomMember).where(RoomMember.room_id == room_id)
        ).all()
        if not members:
            raise SystemExit("방에 참여자가 없다. 먼저 회의실에 입장한 뒤 다시 실행해라.")
        user_ids = [member.user_id for member in members]
        print(f"참여자 {len(user_ids)}명: {[str(u) for u in user_ids]}")

        _purge(db, room_id)

        now = datetime.now(timezone.utc)
        base = now - timedelta(minutes=40)

        topic = Topic(
            room_id=room_id,
            summary=f"{SEED_MARK} 쓰레기 줍는 환경 로봇",
            status=TopicStatus.ACTIVE,
            centroid_embedding=embedder.embed_text("길에 떨어진 쓰레기를 줍는 환경 로봇"),
        )
        db.add(topic)
        db.flush()

        utterances = []
        for index, (speaker, text) in enumerate(PAST_UTTERANCES):
            utterance = Utterance(
                room_id=room_id,
                user_id=user_ids[speaker % len(user_ids)],
                topic_id=topic.topic_id,
                original_text=text,
                normalized_text=text,
                embedding=embedder.embed_text(text),
                state=UtteranceState.REFLECT,
                created_at=base + timedelta(seconds=index * 90),
            )
            db.add(utterance)
            utterances.append(utterance)
        db.flush()

        memory_by_type = {}
        for memory_type, content in MEMORIES:
            memory = SemanticMemory(
                room_id=room_id,
                topic_id=topic.topic_id,
                memory_type=memory_type,
                status=MemoryStatus.ACTIVE,
                content=content,
                embedding=embedder.embed_text(content),
                time_window_start=base,
                time_window_end=now,
            )
            db.add(memory)
            memory_by_type.setdefault(memory_type, memory)
        db.flush()

        fact_by_key = {}
        for key, (fact_type, status, content, evidence) in FACTS.items():
            linked_memory = memory_by_type.get(
                {
                    DesignFactType.CONSTRAINT: SemanticMemoryType.CONSTRAINT,
                    DesignFactType.DECISION: SemanticMemoryType.DECISION,
                    DesignFactType.RATIONALE: SemanticMemoryType.RATIONALE,
                }.get(fact_type)
            )
            fact = DesignFact(
                room_id=room_id,
                topic_id=topic.topic_id,
                semantic_memory_id=(
                    linked_memory.semantic_memory_id if linked_memory else None
                ),
                fact_type=fact_type,
                status=status,
                content=content,
                embedding=embedder.embed_text(content),
            )
            db.add(fact)
            db.flush()
            fact_by_key[key] = fact

            for evidence_index in evidence:
                db.add(
                    DesignFactUtteranceLink(
                        design_fact_id=fact.design_fact_id,
                        utterance_id=utterances[evidence_index].utterance_id,
                        link_role=DesignFactUtteranceLinkRole.SOURCE,
                    )
                )

        for from_key, to_key, link_type in FACT_LINKS:
            db.add(
                DesignFactLink(
                    room_id=room_id,
                    from_fact_id=fact_by_key[from_key].design_fact_id,
                    to_fact_id=fact_by_key[to_key].design_fact_id,
                    link_type=link_type,
                )
            )

        db.commit()
        print(
            f"완료 — 발화 {len(utterances)} / 사실 {len(fact_by_key)} "
            f"/ 링크 {len(FACT_LINKS)} / 기억 {len(MEMORIES)}"
        )
        print(f"topic_id = {topic.topic_id}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _purge(db, room_id: uuid.UUID) -> None:
    """이 방의 기존 데이터를 지운다. 시드를 여러 번 돌려도 깨끗하게 다시 선다."""
    utterance_ids = db.scalars(
        select(Utterance.utterance_id).where(Utterance.room_id == room_id)
    ).all()
    fact_ids = db.scalars(
        select(DesignFact.design_fact_id).where(DesignFact.room_id == room_id)
    ).all()

    # 발화·사실을 참조하는 쪽부터 끊는다(FK 위반 방지).
    db.execute(delete(AgentAlert).where(AgentAlert.room_id == room_id))
    if utterance_ids:
        db.execute(
            delete(UtteranceAnnotation).where(
                UtteranceAnnotation.utterance_id.in_(utterance_ids)
            )
        )
        db.execute(
            delete(NodeUtteranceLink).where(
                NodeUtteranceLink.utterance_id.in_(utterance_ids)
            )
        )
    if fact_ids:
        db.execute(
            delete(DesignFactUtteranceLink).where(
                DesignFactUtteranceLink.design_fact_id.in_(fact_ids)
            )
        )
    db.execute(delete(DesignFactLink).where(DesignFactLink.room_id == room_id))
    db.execute(delete(DesignFact).where(DesignFact.room_id == room_id))
    db.execute(delete(SemanticMemory).where(SemanticMemory.room_id == room_id))
    db.execute(delete(Utterance).where(Utterance.room_id == room_id))
    db.execute(delete(Topic).where(Topic.room_id == room_id))
    db.flush()
    print("기존 데이터 정리 완료")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("사용법: python seed_demo.py <room_id>")
    main(uuid.UUID(sys.argv[1]))
