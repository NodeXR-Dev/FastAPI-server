import asyncio
from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from langsmith import trace

from app.agent.schema.realtime_agent_schema import (
    AgentResponse,
    AlertDraft,
    AnnotationDraft,
    FactRecord,
    GenerationRequest,
    MemoryRecord,
    SourceUtteranceRecord,
)
from app.model.enum import AlertType, DialogueMove, Stance
from app.repository.agent_repository import AgentRepository
from app.schema.agent.ws_event_agent_payload import AgentGuidePayload
from app.schema.websocket.ws_event import AgentGuideWSEvent
from app.service.agent.asset_generation_adapter import AssetGenerationAdapter
from app.db.session import SessionLocal
from app.core.logger import get_logger

logger = get_logger(__name__)


class RealtimeAgentResultService:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        agent_repository: AgentRepository | None = None,
        asset_adapter: AssetGenerationAdapter | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.agent_repository = agent_repository or AgentRepository()
        self.asset_adapter = asset_adapter or AssetGenerationAdapter()

    async def persist_and_build_events(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        utterance_id: UUID,
        topic_id: UUID,
        alerts: list[AlertDraft],
        responses: list[AgentResponse],
        generation_requests: list[GenerationRequest],
        annotation: AnnotationDraft | None = None,
        current_utterance_text: str | None = None,
        current_utterance_created_at: datetime | None = None,
        retrieved_facts: list[FactRecord] | None = None,
        retrieved_memories: list[MemoryRecord] | None = None,
        source_utterances: list[SourceUtteranceRecord] | None = None,
    ) -> list[dict]:
        with trace(
            name="BuildAgentGuideEvents",
            run_type="chain",
            inputs={
                "room_id": str(room_id),
                "utterance_id": str(utterance_id),
                "topic_id": str(topic_id),
                "alert_types": [alert.alert_type for alert in alerts],
                "response_types": [response.response_type for response in responses],
                "generation_asset_types": [
                    request.asset_type for request in generation_requests
                ],
            },
            tags=["realtime-agent", "agent-guide"],
            metadata={"room_id": str(room_id), "topic_id": str(topic_id)},
        ) as guide_trace:
            if annotation is not None:
                await asyncio.to_thread(
                    self._persist_annotation,
                    utterance_id=utterance_id,
                    annotation=annotation,
                )

            persisted_alerts = await asyncio.to_thread(
                self._persist_alerts,
                room_id=room_id,
                utterance_id=utterance_id,
                topic_id=topic_id,
                alerts=alerts,
            )

            generation_responses: list[AgentResponse] = []
            for generation_request in generation_requests:
                try:
                    generation_responses.append(
                        await self.asset_adapter.enqueue(
                            room_id=room_id,
                            user_id=user_id,
                            request=generation_request,
                        )
                    )
                except Exception as error:
                    logger.exception(
                        "[agent_asset_enqueue_failed] room_id=%s | utterance_id=%s | asset_type=%s | error=%s",
                        room_id,
                        utterance_id,
                        generation_request.asset_type,
                        str(error),
                    )
                    generation_responses.append(
                        AgentResponse(
                            response_type="ASSET_GENERATION",
                            message="Asset 생성 요청을 처리하지 못했습니다.",
                        )
                    )

            fact_by_id = {
                item.design_fact_id: item for item in (retrieved_facts or [])
            }
            current_utterance = {
                "text": current_utterance_text,
                "user_id": str(user_id) if user_id else None,
                "created_at": (
                    current_utterance_created_at.isoformat()
                    if current_utterance_created_at
                    else None
                ),
            }

            events = [
                self._guide_event(
                    room_id=room_id,
                    user_id=user_id,
                    guide_id=agent_alert_id,
                    guide_type=alert.alert_type,
                    message=alert.message,
                    evidence=self._evidence(
                        current_utterance=current_utterance,
                        facts=[fact_by_id[alert.related_fact_id]]
                        if alert.related_fact_id in fact_by_id
                        else [],
                        memories=[],
                        utterances=[
                            item
                            for item in (source_utterances or [])
                            if item.design_fact_id == alert.related_fact_id
                        ],
                    ),
                )
                for agent_alert_id, alert in persisted_alerts
            ]
            for response in [*responses, *generation_responses]:
                cited = [
                    fact_by_id[fact_id]
                    for fact_id in response.related_fact_ids
                    if fact_id in fact_by_id
                ]
                cited_utterance_ids = set(response.source_utterance_ids)
                events.append(
                    self._guide_event(
                        room_id=room_id,
                        user_id=user_id,
                        guide_type=self._response_guide_type(response, cited),
                        message=response.message,
                        evidence=self._evidence(
                            current_utterance=current_utterance,
                            facts=cited,
                            memories=retrieved_memories or [],
                            utterances=[
                                item
                                for item in (source_utterances or [])
                                if item.utterance_id in cited_utterance_ids
                            ],
                        ),
                    )
                )
            if guide_trace is not None:
                guide_trace.end(
                    outputs={
                        "agent_guide_count": len(events),
                        "guide_types": [
                            event["payload"]["guide_type"] for event in events
                        ],
                        "persisted_alert_count": len(persisted_alerts),
                        "generation_response_count": len(generation_responses),
                    }
                )
            return events

    @staticmethod
    def _response_guide_type(
        response: AgentResponse,
        cited_facts: list[FactRecord],
    ) -> str:
        """Recall 응답을 스펙의 guide_type으로 옮긴다.

        스펙은 근거가 결정인지 제약인지에 따라 다른 값을 쓴다.
        ASSET_GENERATION은 스펙에 대응값이 없어 그대로 둔다.
        """
        if response.response_type == "CONFLICT_RECALL":
            return AlertType.CONFLICT_RATIONALE_RECALL.value
        if response.response_type == "RATIONALE_RECALL":
            fact_types = {item.fact_type for item in cited_facts}
            if "CONSTRAINT" in fact_types and "DECISION" not in fact_types:
                return AlertType.CONSTRAINT_RATIONALE_RECALL.value
            return AlertType.DECISION_RATIONALE_RECALL.value
        return response.response_type

    @staticmethod
    def _evidence(
        *,
        current_utterance: dict,
        facts: list[FactRecord],
        memories: list[MemoryRecord],
        utterances: list[SourceUtteranceRecord],
    ) -> dict:
        """클라이언트 AGENT_GUIDE 스펙의 evidence 구조로 조립한다."""
        return {
            "current_utterance": current_utterance,
            "related_utterances": [
                {
                    "utterance_id": str(item.utterance_id),
                    "text": item.original_text,
                    "user_id": str(item.user_id) if item.user_id else None,
                    "created_at": (
                        item.created_at.isoformat() if item.created_at else None
                    ),
                }
                for item in utterances
            ],
            "related_facts": [
                {
                    "design_fact_id": str(item.design_fact_id),
                    "fact_type": item.fact_type,
                    "status": item.status,
                    "summary": item.content,
                    "target_scope": item.target_scope,
                    "design_dimension": item.design_dimension,
                }
                for item in facts
            ],
            "related_memories": [
                {
                    "memory_id": str(item.semantic_memory_id),
                    "memory_type": item.memory_type,
                    "status": item.status,
                    "summary": item.content,
                }
                for item in memories
            ],
        }

    def _persist_annotation(
        self,
        *,
        utterance_id: UUID,
        annotation: AnnotationDraft,
    ) -> None:
        """주석 저장 실패가 Agent 응답을 막지 않도록 분리해서 처리한다."""
        db = self.session_factory()
        try:
            self.agent_repository.upsert_annotation(
                db,
                utterance_id=utterance_id,
                dialogue_move=DialogueMove(annotation.dialogue_move),
                stance=Stance(annotation.stance),
                confidence=annotation.confidence,
                model_version=annotation.model_version,
            )
            db.commit()
        except Exception as error:
            db.rollback()
            logger.exception(
                "[agent_annotation_persist_failed] utterance_id=%s | error=%s",
                utterance_id,
                str(error),
            )
        finally:
            db.close()

    def _persist_alerts(
        self,
        *,
        room_id: UUID,
        utterance_id: UUID,
        topic_id: UUID,
        alerts: list[AlertDraft],
    ) -> list[tuple[UUID, AlertDraft]]:
        db = self.session_factory()
        persisted: list[tuple[UUID, AlertDraft]] = []
        try:
            for alert in alerts:
                alert_type = AlertType(alert.alert_type)
                duplicate = self.agent_repository.find_duplicate_alert(
                    db,
                    triggering_utterance_id=utterance_id,
                    related_fact_id=alert.related_fact_id,
                    alert_type=alert_type,
                )
                if duplicate is not None:
                    continue
                entity = self.agent_repository.create_alert(
                    db,
                    room_id=room_id,
                    topic_id=topic_id,
                    triggering_utterance_id=utterance_id,
                    related_fact_id=alert.related_fact_id,
                    alert_type=alert_type,
                    message=alert.message,
                )
                persisted.append((entity.agent_alert_id, alert))
            db.commit()
            return persisted
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _guide_event(
        *,
        room_id: UUID,
        user_id: UUID,
        guide_id: UUID | None = None,
        guide_type: str,
        message: str,
        evidence: dict,
    ) -> dict:
        return AgentGuideWSEvent(
            room_id=room_id,
            user_id=user_id,
            payload=AgentGuidePayload(
                guide_id=guide_id or uuid4(),
                guide_type=guide_type,
                message=message,
                evidence=evidence,
            ),
        ).model_dump(mode="json")
