import uuid
import time

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.logger import get_logger
from app.core.performance import performance_tracker
from app.core.response.code import ResponseCode
from app.core.response.exceptions import NotFoundException
from app.model.enum import UtteranceState
from app.model.memory import Utterance

logger = get_logger(__name__)


class UtteranceRepository:
    def create(
        self,
        db: Session,
        *,
        room_id: uuid.UUID,
        user_id: uuid.UUID,
        original_text: str,
        topic_id: uuid.UUID | None = None,
        normalized_text: str | None = None,
        embedding: list[float] | None = None,
        state: UtteranceState = UtteranceState.NOREFLECT,
    ) -> Utterance:
        stage = "repository_utterance_create"
        start_time = time.perf_counter()

        utterance = Utterance(
            room_id=room_id,
            user_id=user_id,
            topic_id=topic_id,
            original_text=original_text,
            normalized_text=normalized_text,
            embedding=embedding,
            state=state,
        )

        db.add(utterance)
        db.flush()

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        avg_ms = performance_tracker.record(stage, elapsed_ms)

        logger.info(
            "[repository_utterance_create] done | elapsed_ms=%.2f | avg_ms=%.2f | utterance_id=%s",
            elapsed_ms,
            avg_ms,
            utterance.utterance_id,
        )

        return utterance

    def update(
        self,
        db: Session,
        *,
        utterance_id: uuid.UUID,
        topic_id: uuid.UUID | None = None,
        normalized_text: str | None = None,
        embedding: list[float] | None = None,
        state: UtteranceState | None = None,
    ) -> Utterance:
        stage = "repository_utterance_update"
        start_time = time.perf_counter()

        utterance = (
            db.query(Utterance)
            .filter(Utterance.utterance_id == utterance_id)
            .first()
        )

        if utterance is None:
            raise NotFoundException(
                code=ResponseCode.UTT404,
                message="발화를 찾을 수 없습니다.",
            )

        if topic_id is not None:
            utterance.topic_id = topic_id

        if normalized_text is not None:
            utterance.normalized_text = normalized_text

        if embedding is not None:
            utterance.embedding = embedding

        if state is not None:
            utterance.state = state

        db.flush()

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        avg_ms = performance_tracker.record(stage, elapsed_ms)

        logger.info(
            "[repository_utterance_update] done | elapsed_ms=%.2f | avg_ms=%.2f | utterance_id=%s",
            elapsed_ms,
            avg_ms,
            utterance.utterance_id,
        )

        return utterance