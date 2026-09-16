import operator
from datetime import datetime
from typing import Annotated
from uuid import UUID

from typing_extensions import TypedDict

from app.agent.schema.realtime_agent_schema import (
    AgentResponse,
    AlertDraft,
    AnnotationDraft,
    FactLinkRecord,
    FactRecord,
    GenerationRequest,
    GuardResult,
    MemoryRecord,
    SourceUtteranceRecord,
    TriggerResult,
)


class RealtimeAgentState(TypedDict):
    room_id: UUID
    user_id: UUID
    utterance_id: UUID
    original_text: str
    normalized_text: str
    embedding: list[float]
    topic_id: UUID
    is_agent_command: bool | None
    command_text: str
    triggers: TriggerResult
    annotation: AnnotationDraft | None
    created_at: datetime | None
    guard_result: GuardResult
    guard_passed: bool
    retrieved_facts: Annotated[list[FactRecord], operator.add]
    retrieved_memories: Annotated[list[MemoryRecord], operator.add]
    fact_links: Annotated[list[FactLinkRecord], operator.add]
    source_utterances: Annotated[list[SourceUtteranceRecord], operator.add]
    alerts: Annotated[list[AlertDraft], operator.add]
    responses: Annotated[list[AgentResponse], operator.add]
    generation_requests: Annotated[list[GenerationRequest], operator.add]
    ws_events: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]
