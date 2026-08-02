import asyncio
import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session
from langsmith import trace

from app.agent.node.reflection_batch_node import ReflectionBatchNode
from app.agent.schema.reflection_batch_schema import (
    BatchAnalysisResult,
    BatchContext,
    BatchFactRecord,
    BatchGraphEventRecord,
    BatchMemoryRecord,
    BatchTopicRecord,
    BatchUtteranceRecord,
    DedupComparison,
    DedupExistingFact,
    FactCandidate,
    FactDedupDecision,
    FactLinkCandidate,
    FactReference,
    PreparedFactDecision,
    PreparedReflection,
    ReflectionPersistenceResult,
    SemanticMemoryProposal,
    TopicSummaryProposal,
)
from app.core.config import settings
from app.db.session import SessionLocal
from app.model.enum import (
    DesignFactLinkType,
    DesignFactType,
    SemanticMemoryType,
)
from app.model.memory import DesignFact, Utterance
from app.repository.graph_repository import GraphRepository
from app.repository.memory_repository import MemoryRepository
from app.repository.topic_repository import TopicRepository
from app.repository.utterance_repository import UtteranceRepository
from app.service.utterance.embedding_service import EmbeddingService
from app.service.utterance.topic_routing_service import TopicRoutingService


class ReflectionBatchService:
    _GRAPH_EVENT_PAYLOAD_KEYS = {
        "interaction_type",
        "node_id",
        "node_type",
        "node_text",
        "created_node_id",
        "parent_node_id",
        "edge_id",
        "created_edge_id",
        "from_node_id",
        "to_node_id",
        "from_node_type",
        "to_node_type",
        "label",
        "position",
        "before_text",
        "after_text",
        "before_position",
        "after_position",
        "deleted_node_ids",
        "deleted_edge_ids",
        "reference_node_id",
        "reference_id",
    }

    _ALLOWED_LINK_TYPES: dict[
        DesignFactLinkType,
        tuple[set[DesignFactType], set[DesignFactType]],
    ] = {
        DesignFactLinkType.SUPPORTS: (
            {DesignFactType.ARGUMENT_FOR, DesignFactType.RATIONALE},
            {
                DesignFactType.PROPOSAL,
                DesignFactType.DECISION,
                DesignFactType.CONFLICT,
            },
        ),
        DesignFactLinkType.OPPOSES: (
            {DesignFactType.ARGUMENT_AGAINST},
            {
                DesignFactType.PROPOSAL,
                DesignFactType.DECISION,
                DesignFactType.CONFLICT,
            },
        ),
        DesignFactLinkType.CONSTRAINS: (
            {DesignFactType.CONSTRAINT},
            {DesignFactType.PROPOSAL, DesignFactType.DECISION},
        ),
        DesignFactLinkType.CONFLICTS_WITH: (
            {
                DesignFactType.PROPOSAL,
                DesignFactType.DECISION,
                DesignFactType.CONSTRAINT,
                DesignFactType.CONFLICT,
            },
            {
                DesignFactType.PROPOSAL,
                DesignFactType.DECISION,
                DesignFactType.CONSTRAINT,
                DesignFactType.CONFLICT,
            },
        ),
        DesignFactLinkType.RATIONALE_OF: (
            {DesignFactType.RATIONALE},
            {DesignFactType.PROPOSAL, DesignFactType.DECISION},
        ),
        DesignFactLinkType.RESOLVES: (
            {DesignFactType.DECISION},
            {DesignFactType.CONFLICT},
        ),
        DesignFactLinkType.VIOLATES: (
            {DesignFactType.PROPOSAL, DesignFactType.DECISION},
            {DesignFactType.CONSTRAINT},
        ),
    }

    _MEMORY_SOURCE_TYPES: dict[SemanticMemoryType, set[DesignFactType]] = {
        SemanticMemoryType.DECISION: {DesignFactType.DECISION},
        SemanticMemoryType.CONSTRAINT: {DesignFactType.CONSTRAINT},
        SemanticMemoryType.CONFLICT: {
            DesignFactType.CONFLICT,
            DesignFactType.ARGUMENT_FOR,
            DesignFactType.ARGUMENT_AGAINST,
        },
        SemanticMemoryType.RATIONALE: {DesignFactType.RATIONALE},
        SemanticMemoryType.SUMMARY: set(DesignFactType),
    }

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        utterance_repository: UtteranceRepository | None = None,
        graph_repository: GraphRepository | None = None,
        topic_repository: TopicRepository | None = None,
        memory_repository: MemoryRepository | None = None,
        embedding_service: EmbeddingService | None = None,
        topic_routing_service: TopicRoutingService | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.utterance_repository = utterance_repository or UtteranceRepository()
        self.graph_repository = graph_repository or GraphRepository()
        self.topic_repository = topic_repository or TopicRepository()
        self.memory_repository = memory_repository or MemoryRepository()
        self.embedding_service = embedding_service or EmbeddingService()
        self.topic_routing_service = topic_routing_service or TopicRoutingService(
            topic_repository=self.topic_repository,
            utterance_repository=self.utterance_repository,
        )

    def find_pending_room_ids(self) -> list[UUID]:
        db = self.session_factory()
        try:
            room_ids = set(self.utterance_repository.find_unprocessed_room_ids(db))
            room_ids.update(self.graph_repository.find_unprocessed_event_room_ids(db))
            return sorted(room_ids, key=str)
        finally:
            db.close()

    def load_batch_data(
        self,
        *,
        room_id: UUID,
    ) -> tuple[list[BatchUtteranceRecord], list[BatchGraphEventRecord], list[UUID]]:
        db = self.session_factory()
        try:
            utterances = self.utterance_repository.find_unprocessed_by_room(
                db,
                room_id=room_id,
                limit=settings.REFLECTION_BATCH_MAX_UTTERANCES,
            )
            if any(item.topic_id is None for item in utterances):
                self._route_unassigned_utterances(
                    db,
                    room_id=room_id,
                    utterances=utterances,
                )
            graph_events = self.graph_repository.find_unprocessed_events_by_room(
                db,
                room_id=room_id,
                limit=settings.REFLECTION_BATCH_MAX_GRAPH_EVENTS,
            )
            utterance_records = [
                BatchUtteranceRecord(
                    utterance_id=item.utterance_id,
                    user_id=item.user_id,
                    topic_id=item.topic_id,
                    normalized_text=(item.normalized_text or item.original_text).strip(),
                    created_at=item.created_at,
                )
                for item in utterances
            ]
            event_records = [
                BatchGraphEventRecord(
                    graph_event_id=item.graph_event_id,
                    event_type=self._enum_value(item.event_type),
                    node_id=item.node_id,
                    edge_id=item.edge_id,
                    related_fact_id=item.related_fact_id,
                    payload=self._minimal_graph_event_payload(item.payload),
                    created_at=item.created_at,
                )
                for item in graph_events
            ]
            topic_ids = sorted(
                {
                    item.topic_id
                    for item in utterance_records
                    if item.topic_id is not None
                },
                key=str,
            )
            return utterance_records, event_records, topic_ids
        finally:
            db.close()

    def _route_unassigned_utterances(
        self,
        db: Session,
        *,
        room_id: UUID,
        utterances: list[Utterance],
    ) -> None:
        try:
            self.topic_routing_service.lock_room(db, room_id=room_id)
            for utterance in utterances:
                if utterance.topic_id is not None:
                    continue
                normalized_text = (
                    utterance.normalized_text or utterance.original_text
                ).strip()
                embedding = (
                    list(utterance.embedding)
                    if utterance.embedding is not None
                    else self.embedding_service.embed_text(normalized_text)
                )
                if utterance.normalized_text is None or utterance.embedding is None:
                    self.utterance_repository.update(
                        db,
                        utterance_id=utterance.utterance_id,
                        normalized_text=normalized_text,
                        embedding=embedding,
                    )
                self.topic_routing_service.route_topic(
                    db,
                    room_id=room_id,
                    utterance_id=utterance.utterance_id,
                    normalized_text=normalized_text,
                    embedding=embedding,
                    room_locked=True,
                )
            db.commit()
        except Exception:
            db.rollback()
            raise

    def retrieve_related_context(
        self,
        *,
        room_id: UUID,
        topic_ids: list[UUID],
        graph_events: list[BatchGraphEventRecord],
    ) -> tuple[list[BatchTopicRecord], list[BatchFactRecord], list[BatchMemoryRecord]]:
        db = self.session_factory()
        try:
            related_fact_ids = [
                item.related_fact_id
                for item in graph_events
                if item.related_fact_id is not None
            ]
            topics = self.topic_repository.find_by_ids(
                db,
                room_id=room_id,
                topic_ids=topic_ids,
            )
            facts = self.memory_repository.find_batch_facts(
                db,
                room_id=room_id,
                topic_ids=topic_ids,
                related_fact_ids=related_fact_ids,
                limit=settings.REFLECTION_FACT_TOP_K,
            )
            memories = self.memory_repository.find_batch_memories(
                db,
                room_id=room_id,
                topic_ids=topic_ids,
                limit=settings.REFLECTION_MEMORY_TOP_K,
            )
            return (
                [
                    BatchTopicRecord(
                        topic_id=item.topic_id,
                        summary=item.summary,
                        status=item.status,
                    )
                    for item in topics
                ],
                [self._batch_fact_record(item) for item in facts],
                [
                    BatchMemoryRecord(
                        semantic_memory_id=item.semantic_memory_id,
                        topic_id=item.topic_id,
                        memory_type=item.memory_type,
                        content=item.content,
                    )
                    for item in memories
                ],
            )
        finally:
            db.close()

    @staticmethod
    def build_context(
        *,
        room_id: UUID,
        utterances: list[BatchUtteranceRecord],
        graph_events: list[BatchGraphEventRecord],
        topics: list[BatchTopicRecord],
        existing_facts: list[BatchFactRecord],
        semantic_memories: list[BatchMemoryRecord],
    ) -> BatchContext:
        return BatchContext(
            room_id=room_id,
            utterances=utterances,
            graph_events=graph_events,
            topics=topics,
            existing_facts=existing_facts,
            semantic_memories=semantic_memories,
        )

    def validate_analysis(
        self,
        *,
        context: BatchContext,
        analysis: BatchAnalysisResult,
    ) -> BatchAnalysisResult:
        utterance_topic = {
            item.utterance_id: item.topic_id for item in context.utterances
        }
        existing_by_id = {
            item.design_fact_id: item for item in context.existing_facts
        }
        accepted_facts: list[FactCandidate] = []
        seen_temp_ids: set[str] = set()

        for candidate in analysis.facts:
            if candidate.temp_id in seen_temp_ids:
                raise ValueError(f"duplicate fact temp_id={candidate.temp_id}")
            seen_temp_ids.add(candidate.temp_id)
            if candidate.confidence < settings.BATCH_FACT_MIN_CONFIDENCE:
                continue
            source_ids = set(candidate.source_utterance_ids)
            if not source_ids or not source_ids.issubset(utterance_topic):
                raise ValueError(
                    f"fact {candidate.temp_id} references an utterance outside the batch"
                )
            if any(utterance_topic[source_id] != candidate.topic_id for source_id in source_ids):
                raise ValueError(
                    f"fact {candidate.temp_id} topic does not match its source utterances"
                )
            if not set(candidate.related_existing_fact_ids).issubset(existing_by_id):
                raise ValueError(
                    f"fact {candidate.temp_id} references an unknown existing fact"
                )
            accepted_facts.append(candidate)

        candidate_by_id = {item.temp_id: item for item in accepted_facts}
        accepted_links: list[FactLinkCandidate] = []
        for link in analysis.links:
            if link.confidence < settings.BATCH_LINK_MIN_CONFIDENCE:
                continue
            if not self._reference_available(
                link.source,
                candidate_by_id=candidate_by_id,
                existing_by_id=existing_by_id,
            ) or not self._reference_available(
                link.target,
                candidate_by_id=candidate_by_id,
                existing_by_id=existing_by_id,
            ):
                if (
                    link.source.reference_type == "CANDIDATE"
                    and link.source.reference_id in seen_temp_ids
                ) or (
                    link.target.reference_type == "CANDIDATE"
                    and link.target.reference_id in seen_temp_ids
                ):
                    # A relation that depends on a below-threshold fact is discarded too.
                    continue
                raise ValueError("fact link references an unknown fact")
            if link.source == link.target:
                raise ValueError("self fact link is not allowed")
            source_type = self._reference_fact_type(
                link.source,
                candidate_by_id=candidate_by_id,
                existing_by_id=existing_by_id,
            )
            target_type = self._reference_fact_type(
                link.target,
                candidate_by_id=candidate_by_id,
                existing_by_id=existing_by_id,
            )
            allowed_source, allowed_target = self._ALLOWED_LINK_TYPES[link.link_type]
            if source_type not in allowed_source or target_type not in allowed_target:
                raise ValueError(
                    f"invalid fact relationship {source_type.value} "
                    f"-{link.link_type.value}-> {target_type.value}"
                )
            accepted_links.append(link)

        return BatchAnalysisResult(facts=accepted_facts, links=accepted_links)

    async def deduplicate_facts(
        self,
        *,
        room_id: UUID,
        context: BatchContext,
        analysis: BatchAnalysisResult,
        node: ReflectionBatchNode,
    ) -> PreparedReflection:
        with trace(
            name="vector candidate search",
            run_type="retriever",
            inputs={"room_id": str(room_id), "candidate_count": len(analysis.facts)},
        ):
            deterministic, comparisons, embeddings = await asyncio.to_thread(
                self._build_dedup_inputs,
                room_id=room_id,
                facts=analysis.facts,
            )
        judged = await node.judge_dedup(comparisons)
        judged_by_id = self._validate_dedup_judgements(
            comparisons=comparisons,
            decisions=judged.decisions,
        )
        deterministic_by_id = {item.temp_id: item for item in deterministic}
        prepared_decisions: list[PreparedFactDecision] = []
        changed_topic_ids: set[UUID] = set()
        fact_by_id = {item.temp_id: item for item in analysis.facts}
        for fact in analysis.facts:
            decision = deterministic_by_id.get(fact.temp_id) or judged_by_id[fact.temp_id]
            prepared_decisions.append(
                PreparedFactDecision(
                    **decision.model_dump(),
                    embedding=embeddings[fact.temp_id],
                )
            )
            if decision.action != "KEEP_EXISTING":
                changed_topic_ids.add(fact.topic_id)
        if analysis.links:
            existing_topic_by_id = {
                item.design_fact_id: item.topic_id for item in context.existing_facts
            }
            for link in analysis.links:
                for reference in (link.source, link.target):
                    if reference.reference_type == "CANDIDATE":
                        changed_topic_ids.add(
                            fact_by_id[reference.reference_id].topic_id
                        )
                    else:
                        topic_id = existing_topic_by_id.get(
                            self._parse_uuid(reference.reference_id)
                        )
                        if topic_id is not None:
                            changed_topic_ids.add(topic_id)
        return PreparedReflection(
            facts=analysis.facts,
            links=analysis.links,
            decisions=prepared_decisions,
            changed_topic_ids=sorted(changed_topic_ids, key=str),
        )

    def validate_memory_updates(
        self,
        *,
        context: BatchContext,
        prepared: PreparedReflection,
        proposals: list[SemanticMemoryProposal],
    ) -> list[SemanticMemoryProposal]:
        if not proposals:
            return []
        candidate_by_id = {item.temp_id: item for item in prepared.facts}
        existing_by_id = {
            item.design_fact_id: item for item in context.existing_facts
        }
        decision_existing = {
            item.existing_fact_id: candidate_by_id[item.temp_id]
            for item in prepared.decisions
            if item.existing_fact_id is not None
        }
        seen: set[tuple[UUID, object]] = set()
        changed_topics = set(prepared.changed_topic_ids)
        for proposal in proposals:
            if proposal.topic_id not in changed_topics:
                raise ValueError("memory proposal references an unchanged topic")
            key = (proposal.topic_id, proposal.memory_type)
            if key in seen:
                raise ValueError("duplicate memory proposal for topic and type")
            seen.add(key)
            source_types: set[DesignFactType] = set()
            for reference in proposal.source_fact_refs:
                if reference.reference_type == "CANDIDATE":
                    fact = candidate_by_id.get(reference.reference_id)
                else:
                    fact_id = self._parse_uuid(reference.reference_id)
                    fact = existing_by_id.get(fact_id) or decision_existing.get(fact_id)
                if fact is None or fact.topic_id != proposal.topic_id:
                    raise ValueError("memory source fact is invalid for its topic")
                source_types.add(fact.fact_type)
            if not source_types.intersection(
                self._MEMORY_SOURCE_TYPES[proposal.memory_type]
            ):
                raise ValueError("memory type is not grounded in a compatible fact type")
        return proposals

    @staticmethod
    def build_topic_summary_context(
        *,
        context: BatchContext,
        prepared: PreparedReflection,
        memory_updates: list[SemanticMemoryProposal],
    ) -> str:
        changed = set(prepared.changed_topic_ids)
        payload = {
            "topics": [
                item.model_dump(mode="json")
                for item in context.topics
                if item.topic_id in changed
            ],
            "facts": [
                item.model_dump(mode="json")
                for item in prepared.facts
                if item.topic_id in changed
            ],
            "dedup_decisions": [
                item.model_dump(mode="json") for item in prepared.decisions
            ],
            "existing_facts": [
                item.model_dump(mode="json")
                for item in context.existing_facts
                if item.topic_id in changed
            ],
            "links": [item.model_dump(mode="json") for item in prepared.links],
            "memories": [
                item.model_dump(mode="json") for item in memory_updates
            ],
            "existing_memories": [
                item.model_dump(mode="json")
                for item in context.semantic_memories
                if item.topic_id in changed
            ],
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def validate_topic_updates(
        *,
        changed_topic_ids: list[UUID],
        proposals: list[TopicSummaryProposal],
    ) -> list[TopicSummaryProposal]:
        expected = set(changed_topic_ids)
        actual = [item.topic_id for item in proposals]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise ValueError("topic summary output must contain each changed topic exactly once")
        return proposals

    def persist_reflection(
        self,
        *,
        room_id: UUID,
        utterance_ids: list[UUID],
        graph_event_ids: list[UUID],
        prepared: PreparedReflection,
        memory_updates: list[SemanticMemoryProposal],
        topic_updates: list[TopicSummaryProposal],
    ) -> ReflectionPersistenceResult:
        memory_embeddings = {
            index: self.embedding_service.embed_text(item.content)
            for index, item in enumerate(memory_updates)
        }
        db = self.session_factory()
        result = ReflectionPersistenceResult()
        try:
            if self.topic_repository.lock_room(db, room_id=room_id) is None:
                raise ValueError(f"room does not exist: {room_id}")
            locked_utterances = self.utterance_repository.lock_unprocessed_by_ids(
                db,
                room_id=room_id,
                utterance_ids=utterance_ids,
            )
            locked_events = self.graph_repository.lock_unprocessed_events_by_ids(
                db,
                room_id=room_id,
                graph_event_ids=graph_event_ids,
            )
            if len(locked_utterances) != len(utterance_ids):
                raise ValueError("one or more utterances were already reflected")
            if len(locked_events) != len(graph_event_ids):
                raise ValueError("one or more graph events were already processed")

            decision_by_temp = {item.temp_id: item for item in prepared.decisions}
            required_existing_ids = {
                item.existing_fact_id
                for item in prepared.decisions
                if item.existing_fact_id is not None
            }
            required_existing_ids.update(
                self._existing_reference_ids(prepared.links, memory_updates)
            )
            existing_entities = self.memory_repository.find_fact_entities_by_ids(
                db,
                room_id=room_id,
                fact_ids=list(required_existing_ids),
            )
            existing_by_id = {
                item.design_fact_id: item for item in existing_entities
            }
            if set(existing_by_id) != required_existing_ids:
                raise ValueError("an existing fact disappeared before persistence")

            resolved_candidate_facts: dict[str, DesignFact] = {}
            for candidate in prepared.facts:
                decision = decision_by_temp[candidate.temp_id]
                if decision.action == "CREATE":
                    entity = self.memory_repository.create_fact(
                        db,
                        room_id=room_id,
                        topic_id=candidate.topic_id,
                        fact_type=candidate.fact_type,
                        content=candidate.content,
                        embedding=decision.embedding,
                    )
                    result.created_fact_count += 1
                elif decision.action == "KEEP_EXISTING":
                    entity = existing_by_id[decision.existing_fact_id]
                elif decision.action == "UPDATE_EXISTING":
                    entity = self.memory_repository.update_fact(
                        db,
                        fact=existing_by_id[decision.existing_fact_id],
                        content=candidate.content,
                        embedding=decision.embedding,
                    )
                    result.updated_fact_count += 1
                else:
                    self.memory_repository.mark_fact_superseded(
                        existing_by_id[decision.existing_fact_id]
                    )
                    entity = self.memory_repository.create_fact(
                        db,
                        room_id=room_id,
                        topic_id=candidate.topic_id,
                        fact_type=candidate.fact_type,
                        content=candidate.content,
                        embedding=decision.embedding,
                    )
                    result.created_fact_count += 1
                    result.superseded_fact_count += 1
                resolved_candidate_facts[candidate.temp_id] = entity
                for utterance_id in candidate.source_utterance_ids:
                    if self.memory_repository.ensure_fact_utterance_link(
                        db,
                        fact_id=entity.design_fact_id,
                        utterance_id=utterance_id,
                    ):
                        result.fact_utterance_link_count += 1

            for link in prepared.links:
                source = self._resolve_entity_reference(
                    link.source,
                    candidate_facts=resolved_candidate_facts,
                    existing_facts=existing_by_id,
                )
                target = self._resolve_entity_reference(
                    link.target,
                    candidate_facts=resolved_candidate_facts,
                    existing_facts=existing_by_id,
                )
                if source.design_fact_id == target.design_fact_id:
                    continue
                if self.memory_repository.ensure_fact_link(
                    db,
                    room_id=room_id,
                    from_fact_id=source.design_fact_id,
                    to_fact_id=target.design_fact_id,
                    link_type=link.link_type,
                ):
                    result.fact_link_count += 1

            for index, proposal in enumerate(memory_updates):
                memory = self.memory_repository.upsert_semantic_memory(
                    db,
                    room_id=room_id,
                    topic_id=proposal.topic_id,
                    memory_type=proposal.memory_type,
                    content=proposal.content,
                    embedding=memory_embeddings[index],
                )
                source_facts = [
                    self._resolve_entity_reference(
                        reference,
                        candidate_facts=resolved_candidate_facts,
                        existing_facts=existing_by_id,
                    )
                    for reference in proposal.source_fact_refs
                ]
                self.memory_repository.attach_facts_to_memory(
                    source_facts,
                    semantic_memory_id=memory.semantic_memory_id,
                )
                result.memory_update_count += 1

            topic_by_id = {
                item.topic_id: item
                for item in self.topic_repository.find_by_ids(
                    db,
                    room_id=room_id,
                    topic_ids=prepared.changed_topic_ids,
                )
            }
            for update in topic_updates:
                embeddings = self.topic_repository.find_utterance_embeddings(
                    db,
                    room_id=room_id,
                    topic_id=update.topic_id,
                )
                self.topic_repository.update_summary_and_centroid(
                    db,
                    topic=topic_by_id[update.topic_id],
                    summary=update.summary,
                    centroid_embedding=self._mean_embedding(embeddings),
                )
                result.topic_update_count += 1

            processed_at = datetime.now(timezone.utc)
            self.graph_repository.mark_events_processed(
                locked_events,
                processed_at=processed_at,
            )
            self.utterance_repository.mark_reflected(locked_utterances)
            result.processed_graph_event_count = len(locked_events)
            result.reflected_utterance_count = len(locked_utterances)
            db.flush()
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _build_dedup_inputs(
        self,
        *,
        room_id: UUID,
        facts: list[FactCandidate],
    ) -> tuple[list[FactDedupDecision], list[DedupComparison], dict[str, list[float]]]:
        db = self.session_factory()
        deterministic: list[FactDedupDecision] = []
        comparisons: list[DedupComparison] = []
        embeddings: dict[str, list[float]] = {}
        try:
            for fact in facts:
                embedding = self.embedding_service.embed_text(fact.content)
                embeddings[fact.temp_id] = embedding
                matches = self.memory_repository.find_similar_facts(
                    db,
                    room_id=room_id,
                    topic_id=fact.topic_id,
                    fact_type=fact.fact_type,
                    embedding=embedding,
                )
                exact = next(
                    (
                        item
                        for item, _similarity in matches
                        if self._normalize_fact_text(item.content)
                        == self._normalize_fact_text(fact.content)
                    ),
                    None,
                )
                if exact is not None:
                    deterministic.append(
                        FactDedupDecision(
                            temp_id=fact.temp_id,
                            action="KEEP_EXISTING",
                            existing_fact_id=exact.design_fact_id,
                            confidence=1.0,
                        )
                    )
                    continue
                ambiguous = [
                    DedupExistingFact(
                        design_fact_id=item.design_fact_id,
                        topic_id=item.topic_id,
                        fact_type=item.fact_type,
                        status=item.status,
                        content=item.content,
                        similarity=similarity,
                    )
                    for item, similarity in matches
                    if similarity >= settings.FACT_DEDUP_SIMILARITY_THRESHOLD
                ]
                if ambiguous:
                    comparisons.append(
                        DedupComparison(
                            temp_id=fact.temp_id,
                            topic_id=fact.topic_id,
                            fact_type=fact.fact_type,
                            content=fact.content,
                            existing_facts=ambiguous,
                        )
                    )
                else:
                    deterministic.append(
                        FactDedupDecision(
                            temp_id=fact.temp_id,
                            action="CREATE",
                            confidence=1.0,
                        )
                    )
            return deterministic, comparisons, embeddings
        finally:
            db.close()

    @staticmethod
    def _validate_dedup_judgements(
        *,
        comparisons: list[DedupComparison],
        decisions: list[FactDedupDecision],
    ) -> dict[str, FactDedupDecision]:
        expected = {item.temp_id: item for item in comparisons}
        actual = {item.temp_id: item for item in decisions}
        if len(actual) != len(decisions) or set(actual) != set(expected):
            raise ValueError("dedup judge must return exactly one decision per comparison")
        for temp_id, decision in actual.items():
            allowed_ids = {
                item.design_fact_id for item in expected[temp_id].existing_facts
            }
            if decision.action == "CREATE":
                if decision.existing_fact_id is not None:
                    raise ValueError("CREATE dedup decision cannot reference an existing fact")
            elif decision.existing_fact_id not in allowed_ids:
                raise ValueError("dedup judge selected an unknown existing fact")
        return actual

    @classmethod
    def _reference_available(
        cls,
        reference: FactReference,
        *,
        candidate_by_id: dict[str, FactCandidate],
        existing_by_id: dict[UUID, BatchFactRecord],
    ) -> bool:
        if reference.reference_type == "CANDIDATE":
            return reference.reference_id in candidate_by_id
        try:
            return cls._parse_uuid(reference.reference_id) in existing_by_id
        except ValueError:
            return False

    @classmethod
    def _reference_fact_type(
        cls,
        reference: FactReference,
        *,
        candidate_by_id: dict[str, FactCandidate],
        existing_by_id: dict[UUID, BatchFactRecord],
    ) -> DesignFactType:
        if reference.reference_type == "CANDIDATE":
            return candidate_by_id[reference.reference_id].fact_type
        return existing_by_id[cls._parse_uuid(reference.reference_id)].fact_type

    @classmethod
    def _resolve_entity_reference(
        cls,
        reference: FactReference,
        *,
        candidate_facts: dict[str, DesignFact],
        existing_facts: dict[UUID, DesignFact],
    ) -> DesignFact:
        if reference.reference_type == "CANDIDATE":
            return candidate_facts[reference.reference_id]
        return existing_facts[cls._parse_uuid(reference.reference_id)]

    @classmethod
    def _existing_reference_ids(
        cls,
        links: list[FactLinkCandidate],
        memories: list[SemanticMemoryProposal],
    ) -> set[UUID]:
        references = [
            reference
            for link in links
            for reference in (link.source, link.target)
        ]
        references.extend(
            reference
            for memory in memories
            for reference in memory.source_fact_refs
        )
        return {
            cls._parse_uuid(reference.reference_id)
            for reference in references
            if reference.reference_type == "EXISTING"
        }

    @staticmethod
    def _mean_embedding(embeddings: list[list[float]]) -> list[float] | None:
        if not embeddings:
            return None
        dimension = len(embeddings[0])
        if dimension == 0 or any(len(item) != dimension for item in embeddings):
            raise ValueError("topic utterance embeddings have inconsistent dimensions")
        count = len(embeddings)
        return [sum(values) / count for values in zip(*embeddings)]

    @classmethod
    def _minimal_graph_event_payload(cls, raw_payload: str | None) -> dict:
        if not raw_payload:
            return {}
        try:
            value = json.loads(raw_payload)
        except (TypeError, json.JSONDecodeError):
            return {}
        if not isinstance(value, dict):
            return {}
        return {
            key: value[key]
            for key in cls._GRAPH_EVENT_PAYLOAD_KEYS
            if key in value
        }

    @staticmethod
    def _normalize_fact_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()

    @staticmethod
    def _parse_uuid(value: str) -> UUID:
        return UUID(value)

    @staticmethod
    def _batch_fact_record(fact: DesignFact) -> BatchFactRecord:
        return BatchFactRecord(
            design_fact_id=fact.design_fact_id,
            topic_id=fact.topic_id,
            fact_type=fact.fact_type,
            status=fact.status,
            content=fact.content,
        )

    @staticmethod
    def _enum_value(value) -> str:
        return value.value if hasattr(value, "value") else str(value)
