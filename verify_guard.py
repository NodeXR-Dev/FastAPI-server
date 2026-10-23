"""심어둔 제약에 위반 발화가 실제로 걸리는지 확인한다."""
import asyncio, sys, uuid
from app.service.utterance.embedding_service import EmbeddingService
from app.service.agent.memory_retrieval_service import MemoryRetrievalService
from app.agent.subgraph.memory_guard_graph import MemoryGuardGraph
from app.db.session import SessionLocal
from app.model.memory import Topic
from sqlalchemy import select

CASES = [
    "그냥 폭을 1미터로 키워서 한 번에 많이 담자.",
    "배터리랑 모터를 겉에 노출시켜서 달자.",
    "수거통 색깔은 초록색으로 하자.",   # 위반 아님(대조군)
]

async def main(room_id: uuid.UUID) -> None:
    embedder = EmbeddingService()
    db = SessionLocal()
    topic_id = db.scalars(
        select(Topic.topic_id).where(Topic.room_id == room_id)
    ).first()
    db.close()

    retrieval = MemoryRetrievalService()
    guard = MemoryGuardGraph()

    for text in CASES:
        embedding = embedder.embed_text(text)
        facts = retrieval.retrieve_guard_facts(
            room_id=room_id, topic_id=topic_id, embedding=embedding
        )
        print("\n" + "=" * 72)
        print(f"발화: {text}")
        print(f"검색된 제약/결정 {len(facts)}건")
        for fact in facts:
            print(f"   [{fact.fact_type}] sim={fact.similarity:.3f} {fact.content[:44]}")

        state = {
            "room_id": room_id,
            "topic_id": topic_id,
            "utterance_id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "normalized_text": text,
            "embedding": embedding,
            "retrieved_facts": facts,
            "errors": [],
        }
        result = await guard.judge_violation(state)
        verdict = result.get("guard_result")
        if verdict is None:
            print("   판정 실패")
            continue
        alert = verdict.violated and verdict.confidence >= 0.8
        print(f"   >>> 위반={verdict.violated} 유형={verdict.violation_type} "
              f"신뢰도={verdict.confidence} → 알림={'뜸' if alert else '안뜸'}")
        print(f"   >>> 사유: {verdict.reason}")

if __name__ == "__main__":
    asyncio.run(main(uuid.UUID(sys.argv[1])))
