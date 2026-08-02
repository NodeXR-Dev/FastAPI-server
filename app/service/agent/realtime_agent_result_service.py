import asyncio
from collections.abc import Callable
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.agent.schema.realtime_agent_schema import (
    AgentResponse,
    AlertDraft,
    GenerationRequest,
)
from app.model.enum import AlertType
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
    ) -> list[dict]:
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

        events = [
            self._guide_event(
                room_id=room_id,
                user_id=user_id,
                guide_id=agent_alert_id,
                guide_type=alert.alert_type,
                message=alert.message,
                evidence={
                    "agent_alert_id": str(agent_alert_id),
                    "related_fact_id": str(alert.related_fact_id),
                    "confidence": alert.confidence,
                },
            )
            for agent_alert_id, alert in persisted_alerts
        ]
        for response in [*responses, *generation_responses]:
            events.append(
                self._guide_event(
                    room_id=room_id,
                    user_id=user_id,
                    guide_type=response.response_type,
                    message=response.message,
                    evidence={
                        "related_fact_ids": [str(value) for value in response.related_fact_ids],
                        "source_utterance_ids": [
                            str(value) for value in response.source_utterance_ids
                        ],
                    },
                )
            )
        return events

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
