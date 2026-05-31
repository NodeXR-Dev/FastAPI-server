# app/repositories/episode_repository.py

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.meeting import Episode
from app.models.enums import EpisodeStatus


class EpisodeRepository:
    def find_active_by_room_id(
        self,
        db: Session,
        room_id: UUID,
    ) -> Episode | None:
        return (
            db.query(Episode)
            .filter(
                Episode.room_id == room_id,
                Episode.status == EpisodeStatus.ACTIVE,
            )
            .first()
        )