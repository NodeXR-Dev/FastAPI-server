from datetime import datetime
from typing import Literal, Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.validators import NotBlankStr


GuideType = Literal[
    "DECISION_CONFLICT",
    "CONSTRAINT_VIOLATION",
    "LONG_UNRESOLVED_CONFLICT",
    "TOPIC_SHIFT_WITH_UNRESOLVED_CONFLICT",
    "DECISION_RATIONALE_RECALL",
    "CONSTRAINT_RATIONALE_RECALL",
    "CONFLICT_RATIONALE_RECALL",
    "SIMILAR_CONFLICT_REPEATED",
    "PART_GLOBAL_DECISION_CONFLICT",
]


RelatedFactType = Literal[
    "DECISION",
    "CONSTRAINT",
    "CONFLICT",
    "ARGUMENT_FOR",
    "ARGUMENT_AGAINST",
    "RATIONALE",
    "ISSUE",
]


RelatedFactStatus = Literal[
    "ACTIVE",
    "CONFIRMED",
    "RESOLVED",
    "REJECTED",
    "SUPERSEDED",
]


RelatedMemoryType = Literal[
    "SUMMARY",
    "DECISION",
    "CONSTRAINT",
    "CONFLICT",
    "RATIONALE",
]


RelatedMemoryStatus = Literal[
    "ACTIVE",
    "RESOLVED",
    "SUPERSEDED",
]


class CurrentUtteranceEvidence(BaseModel):
    text: NotBlankStr | None = None
    user_id: UUID | None = None
    created_at: datetime | None = None


class RelatedUtteranceEvidence(BaseModel):
    utterance_id: UUID
    text: NotBlankStr
    user_id: UUID | None = None
    created_at: datetime | None = None


class RelatedFactEvidence(BaseModel):
    design_fact_id: UUID
    fact_type: RelatedFactType
    status: RelatedFactStatus
    summary: NotBlankStr
    target_scope: NotBlankStr | None = None
    design_dimension: NotBlankStr | None = None


class RelatedMemoryEvidence(BaseModel):
    memory_id: UUID
    memory_type: RelatedMemoryType
    status: RelatedMemoryStatus
    summary: NotBlankStr


class AgentGuideEvidence(BaseModel):
    current_utterance: CurrentUtteranceEvidence | None = None
    related_utterances: list[RelatedUtteranceEvidence] = Field(default_factory=list)
    related_facts: list[RelatedFactEvidence] = Field(default_factory=list)
    related_memories: list[RelatedMemoryEvidence] = Field(default_factory=list)


class AgentGuidePayload(BaseModel):
    guide_id: UUID
    guide_type: GuideType
    message: NotBlankStr
    evidence: AgentGuideEvidence