import uuid
from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Feature(Base):
    __tablename__ = "features"

    feature_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    feature_text: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_features_room_id", "room_id"),
    )