# app/models/room.py

import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
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
    TopicStatus,
    UtteranceState,
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


class Topic(Base):
    __tablename__ = "topics"

    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    summary: Mapped[str | None] = mapped_column(Text)

    status: Mapped[TopicStatus] = mapped_column(
        Enum(TopicStatus, name="topic_status"),
        nullable=False,
        default=TopicStatus.ACTIVE,
    )

    centroid_embedding = mapped_column(Vector(768))

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
    )

    room: Mapped["Room"] = relationship(back_populates="topics")

    utterances: Mapped[list["Utterance"]] = relationship(
        back_populates="topic",
    )

    __table_args__ = (
        Index("ix_topics_room_id", "room_id"),
        Index("ix_topics_status", "status"),
        Index("ix_topics_room_status", "room_id", "status"),
    )


class Utterance(Base):
    __tablename__ = "utterances"

    utterance_id: Mapped[uuid.UUID] = mapped_column(
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

    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.topic_id"),
    )

    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text)

    embedding = mapped_column(Vector(768))

    state: Mapped[UtteranceState | None] = mapped_column(
        Enum(UtteranceState, name="utterance_state"),
        default=UtteranceState.NOREFLECT,
    )

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    room: Mapped["Room"] = relationship(back_populates="utterances")
    user: Mapped["User"] = relationship(back_populates="utterances")
    topic: Mapped["Topic | None"] = relationship(back_populates="utterances")

    __table_args__ = (
        Index("ix_utterances_room_id", "room_id"),
        Index("ix_utterances_user_id", "user_id"),
        Index("ix_utterances_topic_id", "topic_id"),
        Index("ix_utterances_created_at", "created_at"),
    )