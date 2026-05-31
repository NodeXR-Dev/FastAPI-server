import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.db.base import Base
from app.models.enums import (
    TopicStatus,
    EpisodeStatus,
    DiscussionStatus,
    UtteranceType,
    SemanticMemoryType,
)


class Topic(Base):
    __tablename__ = "topics"

    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TopicStatus] = mapped_column(Enum(TopicStatus), nullable=False, default=TopicStatus.ACTIVE)
    centroid_embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    room = relationship("Room", back_populates="topics")
    discussions = relationship("Discussion", back_populates="topic")
    semantic_memories = relationship("SemanticMemory", back_populates="topic")
    topic_episode_links = relationship("TopicEpisodeLink", back_populates="topic")

    episodes = relationship(
        "Episode",
        secondary="topic_episode_links",
        back_populates="topics",
        viewonly=True,
    )

    __table_args__ = (
        Index("ix_topics_room_id", "room_id"),
        Index("ix_topics_room_id_status", "room_id", "status"),
    )


class Episode(Base):
    __tablename__ = "episodes"

    episode_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)

    status: Mapped[EpisodeStatus] = mapped_column(Enum(EpisodeStatus), nullable=False, default=EpisodeStatus.ACTIVE)

    active_summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    conflict_summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    room = relationship("Room", back_populates="episodes")
    utterances = relationship("Utterance", back_populates="episode")
    semantic_memories = relationship("SemanticMemory", back_populates="episode")
    topic_episode_links = relationship("TopicEpisodeLink", back_populates="episode")

    topics = relationship(
        "Topic",
        secondary="topic_episode_links",
        back_populates="episodes",
        viewonly=True,
    )

    __table_args__ = (
        Index("ix_episodes_room_id", "room_id"),
    )


class TopicEpisodeLink(Base):
    __tablename__ = "topic_episode_links"

    topic_episode_link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.topic_id"), nullable=False)
    episode_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("episodes.episode_id"), nullable=False)

    topic = relationship("Topic", back_populates="topic_episode_links")
    episode = relationship("Episode", back_populates="topic_episode_links")

    __table_args__ = (
        UniqueConstraint(
            "topic_id",
            "episode_id",
            name="uq_topic_episode_links_topic_episode",
        ),
    )


class Utterance(Base):
    __tablename__ = "utterances"

    utterance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    episode_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("episodes.episode_id"), nullable=False)

    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    state: Mapped[UtteranceType | None] = mapped_column(Enum(UtteranceType), nullable=True)

    room = relationship("Room", back_populates="utterances")
    user = relationship("User", back_populates="utterances")
    episode = relationship("Episode", back_populates="utterances")

    discussion_links = relationship("DiscussionUtteranceLink", back_populates="utterance")
    node_links = relationship("NodeUtteranceLink", back_populates="utterance")

    __table_args__ = (
        Index("ix_utterances_room_id", "room_id"),
        Index("ix_utterances_episode_id", "episode_id"),
    )


class Discussion(Base):
    __tablename__ = "discussions"

    discussion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.topic_id"), nullable=False)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    status: Mapped[DiscussionStatus] = mapped_column(
        Enum(DiscussionStatus),
        nullable=False,
        default=DiscussionStatus.ACTIVE,
    )

    room = relationship("Room", back_populates="discussions")
    topic = relationship("Topic", back_populates="discussions")
    utterance_links = relationship("DiscussionUtteranceLink", back_populates="discussion")

    __table_args__ = (
        Index("ix_discussions_room_id", "room_id"),
        Index("ix_discussions_topic_id", "topic_id"),
        Index("ix_discussions_status", "status"),
    )


class DiscussionUtteranceLink(Base):
    __tablename__ = "discussion_utterance_links"

    discussion_utterance_link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    discussion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discussions.discussion_id"),
        nullable=False,
    )

    utterance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("utterances.utterance_id"),
        nullable=False,
    )

    discussion = relationship("Discussion", back_populates="utterance_links")
    utterance = relationship("Utterance", back_populates="discussion_links")

    __table_args__ = (
        UniqueConstraint(
            "discussion_id",
            "utterance_id",
            name="uq_discussion_utterance_links_discussion_utterance",
        ),
    )


class SemanticMemory(Base):
    __tablename__ = "semantic_memories"

    semantic_memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.topic_id"),
        nullable=True,
    )

    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("episodes.episode_id"),
        nullable=True,
    )

    memory_type: Mapped[SemanticMemoryType] = mapped_column(
        Enum(SemanticMemoryType),
        nullable=False,
        default=SemanticMemoryType.SUMMARY,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    importance_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    room = relationship("Room", back_populates="semantic_memories")
    topic = relationship("Topic", back_populates="semantic_memories")
    episode = relationship("Episode", back_populates="semantic_memories")

    __table_args__ = (
        Index("ix_semantic_memories_room_id", "room_id"),
        Index("ix_semantic_memories_topic_id", "topic_id"),
        Index("ix_semantic_memories_episode_id", "episode_id"),
        Index("ix_semantic_memories_memory_type", "memory_type"),
    )