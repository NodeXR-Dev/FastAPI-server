# app/repository/utterance_repository.py

from sqlite3 import IntegrityError
import uuid
import time

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.performance import performance_tracker
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException, NotFoundException, ServerException
from app.model.enum import UtteranceState
from app.model.room import Utterance

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

        stage = "repository_utterance_repository_create"
        start_time = time.perf_counter()

        logger.info(
            "[repository_utterance_repository_create] start | room_id=%s | user_id=%s | utterance_length=%s | state=%s",
            room_id,
            user_id,
            len(original_text),
            state.value,
        )

        try:
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
                "[repository_utterance_repository_create] done | elapsed_ms=%.2f | avg_ms=%.2f | utterance_id=%s",
                elapsed_ms,
                avg_ms,
                utterance.utterance_id,
            )

            return utterance

        except IntegrityError as e:
            db.rollback()

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[repository_utterance_repository_create] integrity_error | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise BadRequestException(
                code=ResponseCode.COMMON400,
                message="발화 생성 요청값이 올바르지 않습니다.",
            )

        except SQLAlchemyError as e:
            db.rollback()

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[repository_utterance_repository_create] db_error | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise ServerException(
                code=ResponseCode.COMMON500,
                message="DB 처리 중 오류가 발생했습니다.",
            )

        except Exception as e:
            db.rollback()

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[repository_utterance_repository_create] failed | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise ServerException(
                code=ResponseCode.COMMON500,
                message="서버 오류가 발생했습니다.",
            )
    
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

        stage = "repository_utterance_repository_update"
        start_time = time.perf_counter()

        logger.info(
            "[repository_utterance_repository_update] start | utterance_id=%s",
            utterance_id,
        )

        try:
            utterance = (
                db.query(Utterance)
                .filter(Utterance.utterance_id == utterance_id)
                .first()
            )

            if utterance is None:
                raise NotFoundException(
                    code=ResponseCode.UTT404
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
                "[repository_utterance_repository_update] done | elapsed_ms=%.2f | avg_ms=%.2f | utterance_id=%s",
                elapsed_ms,
                avg_ms,
                utterance.utterance_id,
            )

            return utterance

        except NotFoundException:
            raise

        except IntegrityError as e:
            db.rollback()

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[repository_utterance_repository_update] integrity_error | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise BadRequestException(
                code=ResponseCode.COMMON400,
                message="발화 업데이트 요청값이 올바르지 않습니다.",
            )

        except SQLAlchemyError as e:
            db.rollback()

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[repository_utterance_repository_update] db_error | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise ServerException(
                code=ResponseCode.COMMON500,
                message="DB 처리 중 오류가 발생했습니다.",
            )

        except Exception as e:
            db.rollback()

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[repository_utterance_repository_update] failed | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise ServerException(
                code=ResponseCode.COMMON500,
                message="서버 오류가 발생했습니다.",
            )