"""meeting_reports.report_data 에 저장하는 구조.

리포트 HTML 은 이 구조만 보고 그린다. 생성 시점의 DB 상태를 그대로 굳혀 두는 것이
목적이라, 이후 fact 가 SUPERSEDED 되거나 그래프가 바뀌어도 리포트는 바뀌지 않는다.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.model.enum import DesignFactStatus, DesignFactType


# Decision Journey 단계 유형. DesignFactType 을 화면용으로 묶은 것이라 enum 을 새로
# 만들지 않고 문자열로 둔다(DB 컬럼이 아니다).
JourneyStepType = Literal[
    "PROPOSAL",
    "ALTERNATIVE",
    "CONSTRAINT",
    "CONFLICT",
    "RATIONALE",
    "DECISION",
]

FinalDecisionSource = Literal[
    "SEMANTIC_MEMORY",
    "DESIGN_FACT",
    "LLM_INFERRED",
    "NONE",
]


class ReportUtteranceEvidence(BaseModel):
    utterance_id: UUID
    speaker_id: UUID
    nickname: str
    text: str
    timestamp: datetime


class DecisionJourneyStep(BaseModel):
    type: JourneyStepType
    fact_type: DesignFactType
    fact_status: DesignFactStatus
    design_fact_id: UUID
    summary: str
    # 최종 결정과 design_fact_links 로 이어져 있는지. 아니면 같은 Topic 의 곁가지 논의다.
    linked_to_decision: bool
    # 가장 먼저 나온 근거 발화. 없으면 None.
    utterance_id: UUID | None = None
    speaker_id: UUID | None = None
    nickname: str | None = None
    timestamp: datetime | None = None
    evidence: list[ReportUtteranceEvidence] = Field(default_factory=list)


class FinalDecision(BaseModel):
    content: str | None = None
    source: FinalDecisionSource = "NONE"
    semantic_memory_id: UUID | None = None
    design_fact_id: UUID | None = None


class DecisionEvidence(BaseModel):
    """Final Decision → 근거. 새 join table 없이 기존 링크 테이블을 따라가 모은 결과다."""

    supporting_utterance_ids: list[UUID] = Field(default_factory=list)
    supporting_design_fact_ids: list[UUID] = Field(default_factory=list)
    supporting_semantic_memory_ids: list[UUID] = Field(default_factory=list)


class MeaningfulUtterance(ReportUtteranceEvidence):
    score: float
    conclusion_relevance: float
    reasoning_influence: float
    information_value: float
    # 이 발화가 Decision Journey 에서 맡은 역할(JourneyStepType). 없으면 빈 목록.
    roles: list[str] = Field(default_factory=list)


class ParticipantDecisionContribution(BaseModel):
    user_id: UUID
    nickname: str
    # Topic 안에서 합계 100 이 되도록 정규화한 값.
    contribution_percent: float = Field(ge=0.0, le=100.0)
    raw_score: float = Field(ge=0.0)
    utterance_count: int = Field(ge=0)
    contributions: list[str] = Field(default_factory=list)


class TopicReport(BaseModel):
    topic_id: UUID
    title: str
    final_decision: FinalDecision
    decision_rationale: str | None = None
    decision_journey: list[DecisionJourneyStep] = Field(default_factory=list)
    evidence: DecisionEvidence = Field(default_factory=DecisionEvidence)
    meaningful_utterances: list[MeaningfulUtterance] = Field(default_factory=list)
    decision_contributions: list[ParticipantDecisionContribution] = Field(
        default_factory=list
    )
    utterance_count: int = 0


class ReportGraphNode(BaseModel):
    node_id: str
    node_type: str
    node_text: str
    parent_node_id: str | None = None
    used_in_generation: bool = False


class ReportGraphEdge(BaseModel):
    edge_id: str
    from_node_id: str
    to_node_id: str
    label: str | None = None
    used_in_generation: bool = False


class FinalOutcome(BaseModel):
    asset_id: UUID
    image_url: str
    image_created_at: datetime | None = None
    # 이미지 생성에 입력된 스냅샷(= 리포트가 근거로 보여주는 그래프).
    graph_snapshot_id: UUID | None = None
    graph_snapshot_version: int | None = None
    graph_captured_at: datetime | None = None
    # 생성 직후 core_2d_image 를 붙여 새로 저장된 스냅샷(assets.graph_snapshot_id).
    result_graph_snapshot_id: UUID | None = None
    result_graph_snapshot_version: int | None = None
    nodes: list[ReportGraphNode] = Field(default_factory=list)
    edges: list[ReportGraphEdge] = Field(default_factory=list)


class OverallParticipation(BaseModel):
    user_id: UUID
    nickname: str
    utterance_count: int = Field(ge=0)
    ratio: float = Field(ge=0.0, le=100.0)


class MeetingOverview(BaseModel):
    room_topic: str
    started_at: datetime | None = None
    ended_at: datetime
    duration_seconds: int = Field(ge=0)
    participants: list[str] = Field(default_factory=list)
    total_utterance_count: int = 0
    topic_count: int = 0


class ContributionScoring(BaseModel):
    conclusion_relevance_weight: float
    reasoning_influence_weight: float
    information_value_weight: float


class MeetingReportData(BaseModel):
    report_id: UUID
    room_id: UUID
    report_version: int
    generated_at: datetime
    overview: MeetingOverview
    final_outcome: FinalOutcome | None = None
    topics: list[TopicReport] = Field(default_factory=list)
    overall_participation: list[OverallParticipation] = Field(default_factory=list)
    scoring: ContributionScoring
    llm_call_count: int = 0
