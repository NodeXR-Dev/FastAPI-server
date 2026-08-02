import uuid
import time

from sqlalchemy import or_, select
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
    @staticmethod
    def unprocessed_condition():
        return or_(
            Utterance.state == UtteranceState.NOREFLECT,
            Utterance.state.is_(None),
        )

    def find_unprocessed_by_room(
        self,
        db: Session,
        *,
        room_id: uuid.UUID,
        limit: int,
        for_update: bool = False,
    ) -> list[Utterance]:
        stmt = (
            select(Utterance)
            .where(
                Utterance.room_id == room_id,
                self.unprocessed_condition(),
            )
            .order_by(Utterance.created_at.asc(), Utterance.utterance_id.asc())
            .limit(limit)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return list(db.scalars(stmt).all())

    def find_unprocessed_room_ids(self, db: Session) -> list[uuid.UUID]:
        stmt = (
            select(Utterance.room_id)
            .where(self.unprocessed_condition())
            .distinct()
            .order_by(Utterance.room_id.asc())
        )
        return list(db.scalars(stmt).all())

    def lock_unprocessed_by_ids(
        self,
        db: Session,
        *,
        room_id: uuid.UUID,
        utterance_ids: list[uuid.UUID],
    ) -> list[Utterance]:
        if not utterance_ids:
            return []
        stmt = (
            select(Utterance)
            .where(
                Utterance.room_id == room_id,
                Utterance.utterance_id.in_(utterance_ids),
                self.unprocessed_condition(),
            )
            .order_by(Utterance.created_at.asc(), Utterance.utterance_id.asc())
            .with_for_update()
        )
        return list(db.scalars(stmt).all())

    def mark_reflected(self, utterances: list[Utterance]) -> None:
        for utterance in utterances:
            utterance.state = UtteranceState.REFLECT

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
