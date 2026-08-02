from collections.abc import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.schema.realtime_agent_schema import (
    FactLinkRecord,
    FactRecord,
    MemoryRecord,
    SourceUtteranceRecord,
)
from app.core.config import settings
from app.db.session import SessionLocal
from app.model.enum import (
    DesignFactLinkType,
    DesignFactStatus,
    DesignFactType,
    SemanticMemoryType,
)
from app.repository.memory_repository import MemoryRepository


class MemoryRetrievalService:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        repository: MemoryRepository | None = None,
        top_k: int | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.repository = repository or MemoryRepository()
        self.top_k = top_k or settings.AGENT_RETRIEVAL_TOP_K

    def retrieve_guard_facts(
        self,
        *,
        room_id: UUID,
        topic_id: UUID,
        embedding: list[float],
    ) -> list[FactRecord]:
        db = self.session_factory()
        try:
            return self.repository.retrieve_facts(
                db,
                room_id=room_id,
                topic_id=topic_id,
                embedding=embedding,
                fact_types=[DesignFactType.DECISION, DesignFactType.CONSTRAINT],
                statuses=[DesignFactStatus.ACTIVE, DesignFactStatus.CONFIRMED],
                top_k=self.top_k,
            )
        finally:
            db.close()

    def retrieve_rationale_seeds(
        self,
        *,
        room_id: UUID,
        topic_id: UUID,
        embedding: list[float],
    ) -> tuple[list[FactRecord], list[MemoryRecord]]:
        db = self.session_factory()
        try:
            seeds = self.repository.retrieve_facts(
                db,
                room_id=room_id,
                topic_id=topic_id,
                embedding=embedding,
                fact_types=[
                    DesignFactType.RATIONALE,
                    DesignFactType.DECISION,
                    DesignFactType.PROPOSAL,
                ],
                statuses=[DesignFactStatus.ACTIVE, DesignFactStatus.CONFIRMED],
                top_k=self.top_k,
            )
            memories = self.repository.retrieve_memories(
                db,
                room_id=room_id,
                topic_id=topic_id,
                embedding=embedding,
                memory_types=[
                    SemanticMemoryType.RATIONALE,
                    SemanticMemoryType.DECISION,
                ],
                top_k=self.top_k,
            )
            return seeds, memories
        finally:
            db.close()

    def retrieve_conflict_seeds(
        self,
        *,
        room_id: UUID,
        topic_id: UUID,
        embedding: list[float],
    ) -> list[FactRecord]:
        db = self.session_factory()
        try:
            seeds = self.repository.retrieve_facts(
                db,
                room_id=room_id,
                topic_id=topic_id,
                embedding=embedding,
                fact_types=[
                    DesignFactType.CONFLICT,
                    DesignFactType.ARGUMENT_FOR,
                    DesignFactType.ARGUMENT_AGAINST,
                ],
                statuses=[
                    DesignFactStatus.ACTIVE,
                    DesignFactStatus.CONFIRMED,
                    DesignFactStatus.REJECTED,
                ],
                top_k=self.top_k,
            )
            return seeds
        finally:
            db.close()

    def retrieve_related_context(
        self,
        *,
        room_id: UUID,
        seed_facts: list[FactRecord],
        link_types: list[DesignFactLinkType],
    ) -> tuple[list[FactRecord], list[FactLinkRecord], list[SourceUtteranceRecord]]:
        db = self.session_factory()
        try:
            related_facts, links, utterances = self.repository.find_related_fact_context(
                db,
                room_id=room_id,
                seed_fact_ids=[fact.design_fact_id for fact in seed_facts],
                link_types=link_types,
            )
            return self._merge_facts(seed_facts, related_facts), links, utterances
        finally:
            db.close()

    @staticmethod
    def _merge_facts(
        primary: list[FactRecord],
        related: list[FactRecord],
    ) -> list[FactRecord]:
        by_id = {fact.design_fact_id: fact for fact in related}
        for fact in primary:
            by_id[fact.design_fact_id] = fact
        return list(by_id.values())
