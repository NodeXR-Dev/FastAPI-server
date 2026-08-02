from typing import TypedDict
from uuid import UUID

from app.agent.schema.reflection_batch_schema import (
    BatchAnalysisResult,
    BatchContext,
    BatchFactRecord,
    BatchGraphEventRecord,
    BatchMemoryRecord,
    BatchTopicRecord,
    BatchUtteranceRecord,
    PreparedReflection,
    ReflectionPersistenceResult,
    SemanticMemoryProposal,
    TopicSummaryProposal,
)


class ReflectionBatchState(TypedDict):
    batch_run_id: UUID
    room_id: UUID
    utterances: list[BatchUtteranceRecord]
    graph_events: list[BatchGraphEventRecord]
    topic_ids: list[UUID]
    topics: list[BatchTopicRecord]
    existing_facts: list[BatchFactRecord]
    semantic_memories: list[BatchMemoryRecord]
    batch_context: BatchContext | None
    analysis_result: BatchAnalysisResult | None
    prepared_reflection: PreparedReflection | None
    memory_updates: list[SemanticMemoryProposal]
    topic_updates: list[TopicSummaryProposal]
    persistence_result: ReflectionPersistenceResult | None

