import asyncio
import time
from uuid import UUID

from langsmith import trace
from sqlalchemy.orm import Session

from app.agent.graph.realtime_agent_graph import (
    RealtimeAgentGraph,
    get_realtime_agent_graph,
)
from app.core.logger import get_logger
from app.core.performance import performance_tracker
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException, NotFoundException
from app.model.enum import UtteranceState
from app.repository.room_repository import RoomRepository
from app.repository.utterance_repository import UtteranceRepository
from app.schema.utterance.ws_event_utterance_payload import AutoUtterancePayload
from app.service.utterance.embedding_service import EmbeddingService
from app.service.utterance.text_preprocess_service import TextPreprocessService
from app.service.utterance.topic_routing_service import TopicRoutingService

logger = get_logger(__name__)


class AutoUtteranceService:
    def __init__(
        self,
        db: Session,
        *,
        text_preprocess_service: TextPreprocessService | None = None,
        embedding_service: EmbeddingService | None = None,
        topic_routing_service: TopicRoutingService | None = None,
        utterance_repository: UtteranceRepository | None = None,
        room_repository: RoomRepository | None = None,
        realtime_agent_graph: RealtimeAgentGraph | None = None,
    ) -> None:
        self.db = db
        self.text_preprocess_service = (
            text_preprocess_service or TextPreprocessService()
        )
        self.embedding_service = embedding_service or EmbeddingService()
        self.topic_routing_service = topic_routing_service or TopicRoutingService()
        self.utterance_repository = utterance_repository or UtteranceRepository()
        self.room_repository = room_repository or RoomRepository()
        self.realtime_agent_graph = realtime_agent_graph or get_realtime_agent_graph()

    async def handle_auto_utterance(
        self,
        *,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> list[dict]:
        started_at = time.perf_counter()
        request = AutoUtterancePayload.model_validate(payload)
        if user_id is None:
            raise BadRequestException(
                code=ResponseCode.BTUTT400,
                message="실시간 발화에는 user_id가 필요합니다.",
            )

        self._validate_room_member(room_id=room_id, user_id=user_id)

        with trace(
            name="RealtimeUtteranceHotPath",
            run_type="chain",
            inputs={
                "room_id": str(room_id),
                "user_id": str(user_id),
                "text_length": len(request.utterance),
            },
            tags=["realtime-agent", "utterance-hot-path"],
            metadata={"room_id": str(room_id)},
        ):
            normalized_text = self.text_preprocess_service.utterance_preprocess(
                request.utterance,
            )
            with trace(
                name="embedding",
                run_type="tool",
                inputs={"text_length": len(normalized_text)},
            ):
                embedding = await asyncio.to_thread(
                    self.embedding_service.embed_text,
                    normalized_text,
                )

            try:
                # FK를 가진 utterance INSERT 전에 room lock을 잡아 동시 centroid
                # 갱신이 lost update/deadlock 없이 같은 순서로 진행되게 한다.
                self.topic_routing_service.lock_room(
                    self.db,
                    room_id=room_id,
                )
                utterance = self.utterance_repository.create(
                    db=self.db,
                    room_id=room_id,
                    user_id=user_id,
                    original_text=request.utterance,
                    normalized_text=normalized_text,
                    embedding=embedding,
                    state=UtteranceState.NOREFLECT,
                )
                with trace(
                    name="topic_routing",
                    run_type="retriever",
                    inputs={
                        "room_id": str(room_id),
                        "utterance_id": str(utterance.utterance_id),
                    },
                ):
                    topic_id = self.topic_routing_service.route_topic(
                        self.db,
                        room_id=room_id,
                        utterance_id=utterance.utterance_id,
                        normalized_text=normalized_text,
                        embedding=embedding,
                        room_locked=True,
                    )
                # Agent는 부가 기능이다. 핵심 발화/Topic 상태를 먼저 확정한다.
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

            agent_events: list[dict] = []
            try:
                agent_state = await self.realtime_agent_graph.ainvoke(
                    room_id=room_id,
                    user_id=user_id,
                    utterance_id=utterance.utterance_id,
                    original_text=request.utterance,
                    normalized_text=normalized_text,
                    embedding=embedding,
                    topic_id=topic_id,
                )
                agent_events = agent_state.get("ws_events", [])
            except Exception as error:
                logger.exception(
                    "[realtime_agent_skipped] room_id=%s | utterance_id=%s | error=%s",
                    room_id,
                    utterance.utterance_id,
                    str(error),
                )

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        performance_tracker.record("realtime_utterance_hot_path", elapsed_ms)
        logger.info(
            "[auto_utterance_completed] room_id=%s | user_id=%s | utterance_id=%s | topic_id=%s | agent_event_count=%s | elapsed_ms=%.2f",
            room_id,
            user_id,
            utterance.utterance_id,
            topic_id,
            len(agent_events),
            elapsed_ms,
        )
        return [
            {
                "event_type": "UTTERANCE_CREATED",
                "room_id": str(room_id),
                "user_id": str(user_id),
                "payload": {
                    "utterance_id": str(utterance.utterance_id),
                    "topic_id": str(topic_id),
                    "utterance": request.utterance,
                },
            },
            *agent_events,
        ]

    def _validate_room_member(self, *, room_id: UUID, user_id: UUID) -> None:
        room = self.room_repository.find_room_by_id(self.db, room_id)
        if room is None:
            raise NotFoundException(code=ResponseCode.ROOM404)
        if not room.is_active:
            raise BadRequestException(
                code=ResponseCode.ROOM400,
                message="비활성화된 회의실에는 발화를 저장할 수 없습니다.",
            )
        member = self.room_repository.find_joined_member_by_user_id(
            self.db,
            room_id=room_id,
            user_id=user_id,
        )
        if member is None:
            raise NotFoundException(code=ResponseCode.ROOM_MEMBER404)
