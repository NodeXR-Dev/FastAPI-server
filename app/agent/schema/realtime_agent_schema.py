from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


AssetIntent = Literal["IMAGE_2D", "MODEL_3D", "REFERENCE", "NONE"]

AgentCommandType = Literal[
    "RATIONALE_RECALL",
    "CONFLICT_RECALL",
    "GENERATE_2D",
    "GENERATE_3D",
    "NONE",
]


class AgentCommandResult(BaseModel):
    """호출어로 Agent를 부른 발화의 명령 종류."""

    command_type: AgentCommandType = "NONE"
    source_asset_id: UUID | None = None


class GuardTriggerResult(BaseModel):
    """호출어가 없는 일반 발화에 대해 제약 검사가 필요한지."""

    memory_guard: bool = False


DialogueMoveLabel = Literal[
    "PROPOSE",
    "DECIDE",
    "ASK",
    "AGREE",
    "DISAGREE",
    "INFORM",
    "OTHER",
]

StanceLabel = Literal["FOR", "AGAINST", "NEUTRAL"]


class UtteranceStructureResult(BaseModel):
    """발화가 무엇을 하는 발화인지에 대한 서술.

    Agent 실행 여부를 묻지 않는다. 그 판단은 코드가 한다.
    """

    dialogue_move: DialogueMoveLabel = "OTHER"
    stance: StanceLabel = "NEUTRAL"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class UtteranceTopicAndStructureResult(BaseModel):
    """발화 1건의 topic 배정과 구조 서술을 한 번에 받는다."""

    topic_number: int = Field(default=0, ge=0)
    new_topic_summary: str = ""
    dialogue_move: DialogueMoveLabel = "OTHER"
    stance: StanceLabel = "NEUTRAL"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class AnnotationDraft(BaseModel):
    """저장 대기 중인 발화 주석."""

    dialogue_move: DialogueMoveLabel
    stance: StanceLabel
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    model_version: str


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
