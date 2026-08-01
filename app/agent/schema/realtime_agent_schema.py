from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


AssetIntent = Literal["IMAGE_2D", "MODEL_3D", "REFERENCE", "NONE"]


class TriggerResult(BaseModel):
    memory_guard: bool = False
    rationale_recall: bool = False
    conflict_recall: bool = False
    asset_generation: bool = False
    asset_type: AssetIntent = "NONE"
    source_asset_id: UUID | None = None


class GuardResult(BaseModel):
    violated: bool = False
    violation_type: Literal["DECISION", "CONSTRAINT", "NONE"] = "NONE"
    related_fact_ids: list[UUID] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""


class FactRecord(BaseModel):
    design_fact_id: UUID
    topic_id: UUID | None = None
    fact_type: str
    status: str
    content: str
    similarity: float | None = None


class MemoryRecord(BaseModel):
    semantic_memory_id: UUID
    topic_id: UUID | None = None
    memory_type: str
    content: str
    similarity: float | None = None


class FactLinkRecord(BaseModel):
    from_fact_id: UUID
    to_fact_id: UUID
    link_type: str


class SourceUtteranceRecord(BaseModel):
    utterance_id: UUID
    design_fact_id: UUID
    link_role: str
    original_text: str


class AlertDraft(BaseModel):
    alert_type: Literal["DECISION_VIOLATION", "CONSTRAINT_VIOLATION"]
    related_fact_id: UUID
    confidence: float
    message: str


class AgentResponse(BaseModel):
    response_type: Literal["RATIONALE_RECALL", "CONFLICT_RECALL", "ASSET_GENERATION"]
    message: str
    related_fact_ids: list[UUID] = Field(default_factory=list)
    source_utterance_ids: list[UUID] = Field(default_factory=list)


class GenerationRequest(BaseModel):
    asset_type: Literal["IMAGE_2D", "MODEL_3D", "REFERENCE"]
    source_asset_id: UUID | None = None
