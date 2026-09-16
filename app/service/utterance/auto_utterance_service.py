import asyncio
import time
from uuid import UUID

from langsmith import trace
from sqlalchemy.orm import Session

from app.agent.schema.realtime_agent_schema import AnnotationDraft
from app.agent.graph.realtime_agent_graph import (
    RealtimeAgentGraph,
    get_realtime_agent_graph,
)
from app.core.config import settings
from app.core.logger import get_logger
from app.core.performance import performance_tracker
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException, NotFoundException
from app.model.enum import UtteranceState
from app.repository.room_repository import RoomRepository
from app.repository.utterance_repository import UtteranceRepository
from app.schema.utterance.ws_event_utterance_payload import AutoUtterancePayload
from app.service.utterance.embedding_service import EmbeddingService
from app.service.utterance.noise_filter_service import (
    FULL_PROCESS,
    NoiseFilterService,
)
from app.service.utterance.text_preprocess_service import TextPreprocessService
from app.service.utterance.topic_routing_service import TopicRoutingService
from app.service.utterance.llm_topic_routing_service import LlmTopicRoutingService
from app.service.utterance.wake_word_service import WakeWordService
from app.service.websocket.connection_manager import (
    RoomConnectionManager,
    room_ws_manager,
)

logger = get_logger(__name__)

# 백그라운드 Agent task가 GC되지 않도록 참조를 유지한다.
_AGENT_TASKS: set[asyncio.Task] = set()


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
        noise_filter_service: NoiseFilterService | None = None,
        wake_word_service: WakeWordService | None = None,
        llm_topic_routing_service: LlmTopicRoutingService | None = None,
        ws_manager: RoomConnectionManager = room_ws_manager,
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
        self.noise_filter_service = noise_filter_service or NoiseFilterService()
        self.wake_word_service = wake_word_service or WakeWordService()
        self._llm_topic_routing_service = llm_topic_routing_service
        self.ws_manager = ws_manager

    @property
    def llm_topic_routing_service(self) -> LlmTopicRoutingService:
        if self._llm_topic_routing_service is None:
            self._llm_topic_routing_service = LlmTopicRoutingService(
                topic_repository=self.topic_routing_service.topic_repository,
                utterance_repository=self.utterance_repository,
                fallback_service=self.topic_routing_service,
            )
        return self._llm_topic_routing_service

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
        ) as realtime_trace:
            normalized_text = self.text_preprocess_service.utterance_preprocess(
                request.utterance,
            )
            noise_decision = FULL_PROCESS
            if settings.NOISE_FILTER_MODE != "off":
                # shadow 모드에서는 판정만 기록하고 처리 흐름은 바꾸지 않는다.
                noise_decision = self.noise_filter_service.classify(
                    normalized_text=normalized_text,
                )
                logger.info(
                    "[noise_filter_shadow] room_id=%s | mode=%s | decision=%s "
                    "| text_length=%s",
                    room_id,
                    settings.NOISE_FILTER_MODE,
                    noise_decision,
                    len(normalized_text),
                )
            wake_word = self.wake_word_service.detect(normalized_text)
            is_agent_command = (
                wake_word.matched and settings.AGENT_WAKE_WORD_REQUIRED
            )
            if wake_word.matched:
                logger.info(
                    "[agent_wake_word_detected] room_id=%s | user_id=%s "
                    "| required=%s | command_text=%s",
                    room_id,
                    user_id,
                    settings.AGENT_WAKE_WORD_REQUIRED,
                    wake_word.command_text,
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
                    state=(
                        UtteranceState.SKIP
                        if is_agent_command
                        else UtteranceState.NOREFLECT
                    ),
                )
                annotation = None
                with trace(
                    name="topic_routing",
                    run_type="retriever",
                    inputs={
                        "room_id": str(room_id),
                        "utterance_id": str(utterance.utterance_id),
                    },
                ):
                    if settings.TOPIC_ROUTING_MODE == "llm":
                        outcome = await self.llm_topic_routing_service.route(
                            self.db,
                            room_id=room_id,
                            utterance_id=utterance.utterance_id,
                            normalized_text=normalized_text,
                            embedding=embedding,
                            room_locked=True,
                        )
                        topic_id = outcome.topic_id
                        # 같은 호출에서 받은 구조 서술을 Agent로 넘겨
                        # 동일 발화를 두 번 분류하지 않는다.
                        annotation = outcome.annotation
                    else:
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
            agent_errors: list[str] = []
            agent_invoked = True
            agent_dispatch = (
                "async" if settings.AGENT_ASYNC_DISPATCH_ENABLED else "inline"
            )
            if agent_dispatch == "async":
                # 발화 응답을 막지 않도록 Agent는 백그라운드에서 실행하고
                # 결과는 AGENT_GUIDE로 따로 push한다.
                self._spawn_agent_task(
                    room_id=room_id,
                    user_id=user_id,
                    utterance_id=utterance.utterance_id,
                    original_text=request.utterance,
                    normalized_text=normalized_text,
                    embedding=embedding,
                    topic_id=topic_id,
                    is_agent_command=is_agent_command,
                    command_text=wake_word.command_text,
                    annotation=annotation,
                )
            else:
                try:
                    agent_state = await self.realtime_agent_graph.ainvoke(
                        room_id=room_id,
                        user_id=user_id,
                        utterance_id=utterance.utterance_id,
                        original_text=request.utterance,
                        normalized_text=normalized_text,
                        embedding=embedding,
                        topic_id=topic_id,
                        is_agent_command=is_agent_command,
                        command_text=wake_word.command_text,
                        annotation=annotation,
                    )
                    agent_events = agent_state.get("ws_events", [])
                    agent_errors = agent_state.get("errors", [])
                except Exception as error:
                    agent_invoked = False
                    agent_errors = ["realtime_agent_invocation_failed"]
                    logger.exception(
                        "[realtime_agent_skipped] room_id=%s | utterance_id=%s | error=%s",
                        room_id,
                        utterance.utterance_id,
                        str(error),
                    )

            guide_events = [
                event
                for event in agent_events
                if event.get("event_type") == "AGENT_GUIDE"
            ]
            if realtime_trace is not None:
                realtime_trace.end(
                    outputs={
                        "utterance_id": str(utterance.utterance_id),
                        "topic_id": str(topic_id),
                        "agent_invoked": agent_invoked,
                        "agent_dispatch": agent_dispatch,
                        "noise_filter_decision": noise_decision,
                        "agent_event_count": len(agent_events),
                        "agent_guide_count": len(guide_events),
                        "guide_types": [
                            event.get("payload", {}).get("guide_type")
                            for event in guide_events
                        ],
                        "agent_error_codes": agent_errors,
                    }
                )

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        performance_tracker.record("realtime_utterance_hot_path", elapsed_ms)
        logger.info(
            "[auto_utterance_completed] room_id=%s | user_id=%s | utterance_id=%s "
            "| topic_id=%s | agent_dispatch=%s | agent_event_count=%s | elapsed_ms=%.2f",
            room_id,
            user_id,
            utterance.utterance_id,
            topic_id,
            agent_dispatch,
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

    def _spawn_agent_task(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        utterance_id: UUID,
        original_text: str,
        normalized_text: str,
        embedding: list[float],
        topic_id: UUID,
        is_agent_command: bool | None = None,
        command_text: str = "",
        annotation: AnnotationDraft | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._run_agent_and_push(
                room_id=room_id,
                user_id=user_id,
                utterance_id=utterance_id,
                original_text=original_text,
                normalized_text=normalized_text,
                embedding=embedding,
                topic_id=topic_id,
                is_agent_command=is_agent_command,
                command_text=command_text,
                annotation=annotation,
            )
        )
        _AGENT_TASKS.add(task)
        task.add_done_callback(_AGENT_TASKS.discard)

    async def _run_agent_and_push(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        utterance_id: UUID,
        original_text: str,
        normalized_text: str,
        embedding: list[float],
        topic_id: UUID,
        is_agent_command: bool | None = None,
        command_text: str = "",
        annotation: AnnotationDraft | None = None,
    ) -> None:
        """WS 요청 세션과 무관하게 Agent를 실행하고 결과 이벤트를 push한다."""
        started_at = time.perf_counter()
        try:
            agent_state = await self.realtime_agent_graph.ainvoke(
                room_id=room_id,
                user_id=user_id,
                utterance_id=utterance_id,
                original_text=original_text,
                normalized_text=normalized_text,
                embedding=embedding,
                topic_id=topic_id,
                is_agent_command=is_agent_command,
                command_text=command_text,
                annotation=annotation,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception(
                "[realtime_agent_async_failed] room_id=%s | utterance_id=%s | error=%s",
                room_id,
                utterance_id,
                str(error),
            )
            return

        events = agent_state.get("ws_events", [])
        errors = agent_state.get("errors", [])

        for event in events:
            try:
                await self.ws_manager.send_to_user(
                    room_id=room_id,
                    user_id=user_id,
                    message=event,
                )
                if settings.ROOM_EVENT_BROADCAST_ENABLED:
                    await self.ws_manager.broadcast(
                        room_id=room_id,
                        message=event,
                        exclude_user_id=user_id,
                    )
            except Exception as error:
                logger.exception(
                    "[realtime_agent_push_failed] room_id=%s | utterance_id=%s "
                    "| event_type=%s | error=%s",
                    room_id,
                    utterance_id,
                    event.get("event_type"),
                    str(error),
                )

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "[realtime_agent_async_completed] room_id=%s | utterance_id=%s "
            "| agent_event_count=%s | agent_error_codes=%s | elapsed_ms=%.2f",
            room_id,
            utterance_id,
            len(events),
            errors,
            elapsed_ms,
        )

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
