from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.agent.schema.realtime_agent_schema import (
    FactLinkRecord,
    FactRecord,
    MemoryRecord,
    SourceUtteranceRecord,
)
from app.model.enum import (
    DesignFactLinkType,
    DesignFactStatus,
    DesignFactType,
    DesignFactUtteranceLinkRole,
    MemoryStatus,
    SemanticMemoryType,
)
from app.model.memory import (
    DesignFact,
    DesignFactLink,
    DesignFactUtteranceLink,
    SemanticMemory,
    Utterance,
)


class MemoryRepository:
    def find_batch_facts(
        self,
        db: Session,
        *,
        room_id: UUID,
        topic_ids: list[UUID],
        related_fact_ids: list[UUID],
        limit: int,
    ) -> list[DesignFact]:
        filters = []
        if topic_ids:
            filters.append(DesignFact.topic_id.in_(topic_ids))
        if related_fact_ids:
            filters.append(DesignFact.design_fact_id.in_(related_fact_ids))
        if not filters:
            return []
        stmt = (
            select(DesignFact)
            .where(
                DesignFact.room_id == room_id,
                DesignFact.status != DesignFactStatus.SUPERSEDED,
                or_(*filters),
            )
            .order_by(DesignFact.created_at.desc(), DesignFact.design_fact_id.asc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    def find_batch_memories(
        self,
        db: Session,
        *,
        room_id: UUID,
        topic_ids: list[UUID],
        limit: int,
    ) -> list[SemanticMemory]:
        if not topic_ids:
            return []
        stmt = (
            select(SemanticMemory)
            .where(
                SemanticMemory.room_id == room_id,
                SemanticMemory.topic_id.in_(topic_ids),
                SemanticMemory.status == MemoryStatus.ACTIVE,
            )
            .order_by(
                SemanticMemory.created_at.desc(),
                SemanticMemory.semantic_memory_id.asc(),
            )
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    def find_fact_entities_by_ids(
        self,
        db: Session,
        *,
        room_id: UUID,
        fact_ids: list[UUID],
    ) -> list[DesignFact]:
        if not fact_ids:
            return []
        stmt = select(DesignFact).where(
            DesignFact.room_id == room_id,
            DesignFact.design_fact_id.in_(fact_ids),
        )
        return list(db.scalars(stmt).all())

    def find_similar_facts(
        self,
        db: Session,
        *,
        room_id: UUID,
        topic_id: UUID,
        fact_type: DesignFactType,
        embedding: list[float],
        limit: int = 3,
    ) -> list[tuple[DesignFact, float]]:
        distance = DesignFact.embedding.cosine_distance(embedding)
        rows = (
            db.query(DesignFact, distance.label("cosine_distance"))
            .filter(
                DesignFact.room_id == room_id,
                DesignFact.topic_id == topic_id,
                DesignFact.fact_type == fact_type,
                DesignFact.status.in_(
                    [DesignFactStatus.ACTIVE, DesignFactStatus.CONFIRMED]
                ),
                DesignFact.embedding.isnot(None),
            )
            .order_by(distance.asc(), DesignFact.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            (fact, max(-1.0, min(1.0, 1.0 - float(cosine_distance))))
            for fact, cosine_distance in rows
        ]

    def create_fact(
        self,
        db: Session,
        *,
        room_id: UUID,
        topic_id: UUID,
        fact_type: DesignFactType,
        content: str,
        embedding: list[float],
    ) -> DesignFact:
        fact = DesignFact(
            room_id=room_id,
            topic_id=topic_id,
            fact_type=fact_type,
            status=DesignFactStatus.ACTIVE,
            content=content,
            embedding=embedding,
        )
        db.add(fact)
        db.flush()
        return fact

    def update_fact(
        self,
        db: Session,
        *,
        fact: DesignFact,
        content: str,
        embedding: list[float],
    ) -> DesignFact:
        fact.content = content
        fact.embedding = embedding
        db.flush()
        return fact

    def mark_fact_superseded(self, fact: DesignFact) -> None:
        fact.status = DesignFactStatus.SUPERSEDED

    def ensure_fact_utterance_link(
        self,
        db: Session,
        *,
        fact_id: UUID,
        utterance_id: UUID,
        role: DesignFactUtteranceLinkRole = DesignFactUtteranceLinkRole.SOURCE,
    ) -> bool:
        existing = db.scalar(
            select(DesignFactUtteranceLink).where(
                DesignFactUtteranceLink.design_fact_id == fact_id,
                DesignFactUtteranceLink.utterance_id == utterance_id,
                DesignFactUtteranceLink.link_role == role,
            )
        )
        if existing is not None:
            return False
        db.add(
            DesignFactUtteranceLink(
                design_fact_id=fact_id,
                utterance_id=utterance_id,
                link_role=role,
            )
        )
        db.flush()
        return True

    def ensure_fact_link(
        self,
        db: Session,
        *,
        room_id: UUID,
        from_fact_id: UUID,
        to_fact_id: UUID,
        link_type: DesignFactLinkType,
    ) -> bool:
        existing = db.scalar(
            select(DesignFactLink).where(
                DesignFactLink.from_fact_id == from_fact_id,
                DesignFactLink.to_fact_id == to_fact_id,
                DesignFactLink.link_type == link_type,
            )
        )
        if existing is not None:
            return False
        db.add(
            DesignFactLink(
                room_id=room_id,
                from_fact_id=from_fact_id,
                to_fact_id=to_fact_id,
                link_type=link_type,
            )
        )
        db.flush()
        return True

    def upsert_semantic_memory(
        self,
        db: Session,
        *,
        room_id: UUID,
        topic_id: UUID,
        memory_type: SemanticMemoryType,
        content: str,
        embedding: list[float],
    ) -> SemanticMemory:
        memory = db.scalar(
            select(SemanticMemory)
            .where(
                SemanticMemory.room_id == room_id,
                SemanticMemory.topic_id == topic_id,
                SemanticMemory.memory_type == memory_type,
                SemanticMemory.status == MemoryStatus.ACTIVE,
            )
            .order_by(SemanticMemory.created_at.desc())
            .limit(1)
        )
        if memory is None:
            memory = SemanticMemory(
                room_id=room_id,
                topic_id=topic_id,
                memory_type=memory_type,
                status=MemoryStatus.ACTIVE,
                content=content,
                embedding=embedding,
            )
            db.add(memory)
        else:
            memory.content = content
            memory.embedding = embedding
        db.flush()
        return memory

    def attach_facts_to_memory(
        self,
        facts: list[DesignFact],
        *,
        semantic_memory_id: UUID,
    ) -> None:
        for fact in facts:
            fact.semantic_memory_id = semantic_memory_id

    def retrieve_facts(
        self,
        db: Session,
        *,
        room_id: UUID,
        topic_id: UUID | None,
        embedding: list[float],
        fact_types: Iterable[DesignFactType],
        statuses: Iterable[DesignFactStatus],
        top_k: int,
    ) -> list[FactRecord]:
        fact_types = list(fact_types)
        statuses = list(statuses)
        topic_order = case(
            (DesignFact.topic_id == topic_id, 0),
            else_=1,
        )
        distance = DesignFact.embedding.cosine_distance(embedding)
        rows = (
            db.query(DesignFact, distance.label("cosine_distance"))
            .filter(
                DesignFact.room_id == room_id,
                DesignFact.fact_type.in_(fact_types),
                DesignFact.status.in_(statuses),
                DesignFact.embedding.isnot(None),
            )
            .order_by(topic_order.asc(), distance.asc(), DesignFact.created_at.desc())
            .limit(top_k)
            .all()
        )
        records = [
            self._fact_record(fact, similarity=1.0 - float(cosine_distance))
            for fact, cosine_distance in rows
        ]
        return self._append_fact_fallback(
            db,
            records=records,
            room_id=room_id,
            topic_id=topic_id,
            fact_types=fact_types,
            statuses=statuses,
            top_k=top_k,
        )

    def retrieve_memories(
        self,
        db: Session,
        *,
        room_id: UUID,
        topic_id: UUID | None,
        embedding: list[float],
        memory_types: Iterable[SemanticMemoryType],
        top_k: int,
    ) -> list[MemoryRecord]:
        memory_types = list(memory_types)
        topic_order = case(
            (SemanticMemory.topic_id == topic_id, 0),
            else_=1,
        )
        distance = SemanticMemory.embedding.cosine_distance(embedding)
        rows = (
            db.query(SemanticMemory, distance.label("cosine_distance"))
            .filter(
                SemanticMemory.room_id == room_id,
                SemanticMemory.memory_type.in_(memory_types),
                SemanticMemory.status == MemoryStatus.ACTIVE,
                SemanticMemory.embedding.isnot(None),
            )
            .order_by(topic_order.asc(), distance.asc(), SemanticMemory.created_at.desc())
            .limit(top_k)
            .all()
        )
        records = [
            self._memory_record(memory, similarity=1.0 - float(cosine_distance))
            for memory, cosine_distance in rows
        ]
        return self._append_memory_fallback(
            db,
            records=records,
            room_id=room_id,
            topic_id=topic_id,
            memory_types=memory_types,
            top_k=top_k,
        )

    def find_related_fact_context(
        self,
        db: Session,
        *,
        room_id: UUID,
        seed_fact_ids: list[UUID],
        link_types: Iterable[DesignFactLinkType],
    ) -> tuple[list[FactRecord], list[FactLinkRecord], list[SourceUtteranceRecord]]:
        if not seed_fact_ids:
            return [], [], []

        links = (
            db.query(DesignFactLink)
            .filter(
                DesignFactLink.room_id == room_id,
                DesignFactLink.link_type.in_(list(link_types)),
                or_(
                    DesignFactLink.from_fact_id.in_(seed_fact_ids),
                    DesignFactLink.to_fact_id.in_(seed_fact_ids),
                ),
            )
            .order_by(DesignFactLink.created_at.asc())
            .all()
        )
        related_ids = set(seed_fact_ids)
        for link in links:
            related_ids.add(link.from_fact_id)
            related_ids.add(link.to_fact_id)

        facts = (
            db.query(DesignFact)
            .filter(
                DesignFact.room_id == room_id,
                DesignFact.design_fact_id.in_(related_ids),
            )
            .order_by(DesignFact.created_at.asc())
            .all()
        )
        source_rows = (
            db.query(DesignFactUtteranceLink, Utterance)
            .join(
                Utterance,
                Utterance.utterance_id == DesignFactUtteranceLink.utterance_id,
            )
            .filter(
                Utterance.room_id == room_id,
                DesignFactUtteranceLink.design_fact_id.in_(related_ids),
            )
            .order_by(Utterance.created_at.asc())
            .all()
        )
        return (
            [self._fact_record(fact) for fact in facts],
            [
                FactLinkRecord(
                    from_fact_id=link.from_fact_id,
                    to_fact_id=link.to_fact_id,
                    link_type=self._enum_value(link.link_type),
                )
                for link in links
            ],
            [
                SourceUtteranceRecord(
                    utterance_id=utterance.utterance_id,
                    design_fact_id=link.design_fact_id,
                    link_role=self._enum_value(link.link_role),
                    original_text=utterance.original_text,
                )
                for link, utterance in source_rows
            ],
        )

    def _append_fact_fallback(
        self,
        db: Session,
        *,
        records: list[FactRecord],
        room_id: UUID,
        topic_id: UUID | None,
        fact_types: list[DesignFactType],
        statuses: list[DesignFactStatus],
        top_k: int,
    ) -> list[FactRecord]:
        if len(records) >= top_k:
            return records

        existing_ids = [record.design_fact_id for record in records]
        query = db.query(DesignFact).filter(
            DesignFact.room_id == room_id,
            DesignFact.fact_type.in_(fact_types),
            DesignFact.status.in_(statuses),
        )
        if existing_ids:
            query = query.filter(DesignFact.design_fact_id.notin_(existing_ids))
        fallback = (
            query.order_by(
                case((DesignFact.topic_id == topic_id, 0), else_=1).asc(),
                DesignFact.created_at.desc(),
            )
            .limit(top_k - len(records))
            .all()
        )
        return [*records, *(self._fact_record(fact) for fact in fallback)]

    def _append_memory_fallback(
        self,
        db: Session,
        *,
        records: list[MemoryRecord],
        room_id: UUID,
        topic_id: UUID | None,
        memory_types: list[SemanticMemoryType],
        top_k: int,
    ) -> list[MemoryRecord]:
        if len(records) >= top_k:
            return records

        existing_ids = [record.semantic_memory_id for record in records]
        query = db.query(SemanticMemory).filter(
            SemanticMemory.room_id == room_id,
            SemanticMemory.memory_type.in_(memory_types),
            SemanticMemory.status == MemoryStatus.ACTIVE,
        )
        if existing_ids:
            query = query.filter(
                SemanticMemory.semantic_memory_id.notin_(existing_ids),
            )
        fallback = (
            query.order_by(
                case((SemanticMemory.topic_id == topic_id, 0), else_=1).asc(),
                SemanticMemory.created_at.desc(),
            )
            .limit(top_k - len(records))
            .all()
        )
        return [*records, *(self._memory_record(memory) for memory in fallback)]

    def _fact_record(
        self,
        fact: DesignFact,
        *,
        similarity: float | None = None,
    ) -> FactRecord:
        return FactRecord(
            design_fact_id=fact.design_fact_id,
            topic_id=fact.topic_id,
            fact_type=self._enum_value(fact.fact_type),
            status=self._enum_value(fact.status),
            content=fact.content,
            similarity=similarity,
        )

    def _memory_record(
        self,
        memory: SemanticMemory,
        *,
        similarity: float | None = None,
    ) -> MemoryRecord:
        return MemoryRecord(
            semantic_memory_id=memory.semantic_memory_id,
            topic_id=memory.topic_id,
            memory_type=self._enum_value(memory.memory_type),
            content=memory.content,
            similarity=similarity,
        )

    @staticmethod
    def _enum_value(value) -> str:
        return value.value if hasattr(value, "value") else str(value)
