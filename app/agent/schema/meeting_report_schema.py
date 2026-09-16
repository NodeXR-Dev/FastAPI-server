from uuid import UUID

from pydantic import BaseModel, Field


class TopicFactContext(BaseModel):
    fact_type: str
    status: str
    content: str


class TopicDecisionContext(BaseModel):
    topic_id: UUID
    topic_summary: str | None = None
    facts: list[TopicFactContext] = Field(default_factory=list)


class InferredTopicDecision(BaseModel):
    topic_id: UUID
    # 팀이 한 방향으로 모이지 않았으면 null.
    decision: str | None = None
    rationale: str | None = None


class InferredTopicDecisionBundle(BaseModel):
    decisions: list[InferredTopicDecision] = Field(default_factory=list)
