from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.model.enum import (
    DesignFactLinkType,
    DesignFactStatus,
    DesignFactType,
    SemanticMemoryType,
    TopicStatus,
)


class BatchUtteranceRecord(BaseModel):
    utterance_id: UUID
    user_id: UUID
    topic_id: UUID | None = None
    normalized_text: str
    created_at: datetime | None = None


class BatchGraphEventRecord(BaseModel):
    graph_event_id: UUID
    event_type: str
    node_id: UUID | None = None
    edge_id: UUID | None = None
    related_fact_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class BatchTopicRecord(BaseModel):
    topic_id: UUID
    summary: str | None = None
    status: TopicStatus


class BatchFactRecord(BaseModel):
    design_fact_id: UUID
    topic_id: UUID | None = None
    fact_type: DesignFactType
    status: DesignFactStatus
    content: str


class BatchMemoryRecord(BaseModel):
    semantic_memory_id: UUID
    topic_id: UUID | None = None
    memory_type: SemanticMemoryType
    content: str


class BatchContext(BaseModel):
    room_id: UUID
    utterances: list[BatchUtteranceRecord] = Field(default_factory=list)
    graph_events: list[BatchGraphEventRecord] = Field(default_factory=list)
    topics: list[BatchTopicRecord] = Field(default_factory=list)
    existing_facts: list[BatchFactRecord] = Field(default_factory=list)
    semantic_memories: list[BatchMemoryRecord] = Field(default_factory=list)


class FactCandidate(BaseModel):
    temp_id: str = Field(min_length=1, max_length=80)
    topic_id: UUID
    fact_type: DesignFactType
    content: str = Field(min_length=1)
    source_utterance_ids: list[UUID] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    related_existing_fact_ids: list[UUID] = Field(default_factory=list)

    @field_validator("temp_id", "content")
    @classmethod
    def strip_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class FactReference(BaseModel):
    reference_type: Literal["EXISTING", "CANDIDATE"]
    reference_id: str = Field(min_length=1)


class FactLinkCandidate(BaseModel):
    source: FactReference
    target: FactReference
    link_type: DesignFactLinkType
    confidence: float = Field(ge=0.0, le=1.0)


class BatchAnalysisResult(BaseModel):
    facts: list[FactCandidate] = Field(default_factory=list)
    links: list[FactLinkCandidate] = Field(default_factory=list)


class DedupExistingFact(BaseModel):
    design_fact_id: UUID
    topic_id: UUID | None = None
    fact_type: DesignFactType
    status: DesignFactStatus
    content: str
    similarity: float = Field(ge=-1.0, le=1.0)


class DedupComparison(BaseModel):
    temp_id: str
    topic_id: UUID
    fact_type: DesignFactType
    content: str
    existing_facts: list[DedupExistingFact]


class FactDedupDecision(BaseModel):
    temp_id: str
    action: Literal[
        "CREATE",
        "KEEP_EXISTING",
        "UPDATE_EXISTING",
        "SUPERSEDE_EXISTING",
    ]
    existing_fact_id: UUID | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class FactDedupJudgeResult(BaseModel):
    decisions: list[FactDedupDecision] = Field(default_factory=list)


class PreparedFactDecision(FactDedupDecision):
    embedding: list[float]


class PreparedReflection(BaseModel):
    facts: list[FactCandidate] = Field(default_factory=list)
    links: list[FactLinkCandidate] = Field(default_factory=list)
    decisions: list[PreparedFactDecision] = Field(default_factory=list)
    changed_topic_ids: list[UUID] = Field(default_factory=list)


class SemanticMemoryProposal(BaseModel):
    topic_id: UUID
    memory_type: SemanticMemoryType
    content: str = Field(min_length=1)
    source_fact_refs: list[FactReference] = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class SemanticMemoryProposalBundle(BaseModel):
    memories: list[SemanticMemoryProposal] = Field(default_factory=list)


class TopicSummaryProposal(BaseModel):
    topic_id: UUID
    summary: str = Field(min_length=1)

    @field_validator("summary")
    @classmethod
    def strip_summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("summary must not be blank")
        return value


class TopicSummaryProposalBundle(BaseModel):
    topics: list[TopicSummaryProposal] = Field(default_factory=list)


class ReflectionPersistenceResult(BaseModel):
    created_fact_count: int = 0
    updated_fact_count: int = 0
    superseded_fact_count: int = 0
    fact_utterance_link_count: int = 0
    fact_link_count: int = 0
    memory_update_count: int = 0
    topic_update_count: int = 0
    reflected_utterance_count: int = 0
    processed_graph_event_count: int = 0
