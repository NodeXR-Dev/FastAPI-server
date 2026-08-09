from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.model.memory import Utterance
from app.model.room import RoomMember, User


class ReportRepository:
    def find_participant_utterance_counts(
        self,
        db: Session,
        *,
        room_id: UUID,
        started_at: datetime,
        requested_at: datetime,
    ) -> list[tuple[UUID, str, int]]:
        stmt = (
            select(
                RoomMember.user_id,
                User.nickname,
                func.count(Utterance.utterance_id),
            )
            .join(User, User.user_id == RoomMember.user_id)
            .outerjoin(
                Utterance,
                and_(
                    Utterance.room_id == RoomMember.room_id,
                    Utterance.user_id == RoomMember.user_id,
                    Utterance.created_at >= started_at,
                    Utterance.created_at <= requested_at,
                ),
            )
            .where(RoomMember.room_id == room_id)
            .group_by(RoomMember.user_id, User.nickname)
            .order_by(User.nickname.asc(), RoomMember.user_id.asc())
        )
        return [
            (user_id, nickname, int(utterance_count))
            for user_id, nickname, utterance_count in db.execute(stmt).all()
        ]
