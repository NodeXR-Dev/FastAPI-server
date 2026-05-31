# app/repositories/utterance_repository.py

import uuid
import time

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.performance import performance_tracker
from app.models.enums import UtteranceType
from app.models.meeting import Utterance

logger = get_logger(__name__)


class UtteranceRepository:
    def create(
        self,
        db: Session,
        *,
        room_id: uuid.UUID,
        user_id: uuid.UUID,
        episode_id: uuid.UUID,
        original_text: str,
        normalized_text: str,
        embedding: list[float],
        state: UtteranceType,
    ) -> Utterance:
        """
        utterances 테이블에 발화를 저장한다.
        """

        stage = "db_utterance_create"
        start_time = time.perf_counter()

        logger.info(
            "[db_utterance_create] start | room_id=%s | user_id=%s | episode_id=%s | state=%s",
            room_id,
            user_id,
            episode_id,
            state.value,
        )

        try:
            utterance = Utterance(
                room_id=room_id,
                user_id=user_id,
                episode_id=episode_id,
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
                "[db_utterance_create] done | elapsed_ms=%.2f | avg_ms=%.2f | utterance_id=%s",
                elapsed_ms,
                avg_ms,
                utterance.utterance_id,
            )

            return utterance

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[db_utterance_create] failed | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise