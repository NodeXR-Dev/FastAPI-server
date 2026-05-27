import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RoomMemberRole, RoomMemberState


class Room(Base):
    __tablename__ = "rooms"

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    topic: Mapped[str] = mapped_column(String, nullable=False)
    room_password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    members = relationship("RoomMember", back_populates="room")
    topics = relationship("Topic", back_populates="room")
    episodes = relationship("Episode", back_populates="room")
    utterances = relationship("Utterance", back_populates="room")
    discussions = relationship("Discussion", back_populates="room")
    sub_graphs = relationship("SubGraph", back_populates="room")
    nodes = relationship("Node", back_populates="room")
    edges = relationship("Edge", back_populates="room")
    graph_snapshots = relationship("GraphSnapshot", back_populates="room")
    assets = relationship("Asset", back_populates="room")
    references = relationship("Reference", back_populates="room")


class RoomMember(Base):
    __tablename__ = "room_members"

    room_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id"),
        nullable=False,
    )

    role: Mapped[RoomMemberRole] = mapped_column(
        Enum(RoomMemberRole),
        nullable=False,
    )

    state: Mapped[RoomMemberState] = mapped_column(
        Enum(RoomMemberState),
        nullable=False,
    )

    room = relationship("Room", back_populates="members")
    user = relationship("User", back_populates="room_members")

    __table_args__ = (
        UniqueConstraint(
            "room_id",
            "user_id",
            name="uq_room_members_room_id_user_id",
        ),
    )