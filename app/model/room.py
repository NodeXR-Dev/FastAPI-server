import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.db.base import Base
from app.model.enum import (
    RoomMemberRole,
    RoomMemberState,
)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    nickname: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    room_members: Mapped[list["RoomMember"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    utterances: Mapped[list["Utterance"]] = relationship(
        back_populates="user",
    )


class Room(Base):
    __tablename__ = "rooms"

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    topic: Mapped[str] = mapped_column(String, nullable=False)
    room_password_hash: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    members: Mapped[list["RoomMember"]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
    )

    topics: Mapped[list["Topic"]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
    )

    utterances: Mapped[list["Utterance"]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
    )


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
        Enum(RoomMemberRole, name="room_member_role"),
        nullable=False,
    )

    state: Mapped[RoomMemberState] = mapped_column(
        Enum(RoomMemberState, name="room_member_state"),
        nullable=False,
    )

    room: Mapped["Room"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="room_members")

    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_room_members_room_user"),
    )