import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.db.base import Base
from app.models.enums import (
    TopicStatus,
    EpisodeStatus,
    DecisionStatus,
    UtteranceType,
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

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[TopicStatus] = mapped_column(
        Enum(TopicStatus),
        nullable=False,
        default=TopicStatus.ACTIVE,
    )

    centroid_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536),
        nullable=True,
    )

    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    room = relationship("Room", back_populates="topics")
    episodes = relationship("Episode", back_populates="topic")
    discussions = relationship("Discussion", back_populates="topic")
    topic_episode_links = relationship("TopicEpisodeLink", back_populates="topic")

    __table_args__ = (
        Index("ix_topics_room_id", "room_id"),
        Index("ix_topics_room_id_status", "room_id", "status"),
    )


class Episode(Base):
    __tablename__ = "episodes"

    episode_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.topic_id"),
        nullable=False,
    )

    status: Mapped[EpisodeStatus] = mapped_column(
        Enum(EpisodeStatus),
        nullable=False,
        default=EpisodeStatus.ACTIVE,
    )

    active_summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    conflict_summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    room = relationship("Room", back_populates="episodes")
    topic = relationship("Topic", back_populates="episodes")
    utterances = relationship("Utterance", back_populates="episode")
    topic_episode_links = relationship("TopicEpisodeLink", back_populates="episode")

    __table_args__ = (
        Index("ix_episodes_room_id", "room_id"),
        Index("ix_episodes_topic_id", "topic_id"),
    )


class TopicEpisodeLink(Base):
    __tablename__ = "topic_episode_links"

    topic_episode_link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.topic_id"),
        nullable=False,
    )

    episode_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("episodes.episode_id"),
        nullable=False,
    )

    topic = relationship("Topic", back_populates="topic_episode_links")
    episode = relationship("Episode", back_populates="topic_episode_links")


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

    episode_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("episodes.episode_id"),
        nullable=False,
    )

    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536),
        nullable=True,
    )

    state: Mapped[UtteranceType | None] = mapped_column(
        Enum(UtteranceType),
        nullable=True,
    )

    room = relationship("Room", back_populates="utterances")
    user = relationship("User", back_populates="utterances")
    episode = relationship("Episode", back_populates="utterances")

    decision_links = relationship("DecisionUtteranceLink", back_populates="utterance")
    node_links = relationship("NodeUtteranceLink", back_populates="utterance")

    __table_args__ = (
        Index("ix_utterances_room_id", "room_id"),
        Index("ix_utterances_episode_id", "episode_id"),
    )


class Discussion(Base):
    __tablename__ = "discussions"

    discussion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.topic_id"),
        nullable=False,
    )

    statement: Mapped[str | None] = mapped_column(Text, nullable=True)

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536),
        nullable=True,
    )

    status: Mapped[DecisionStatus] = mapped_column(
        Enum(DecisionStatus),
        nullable=False,
        default=DecisionStatus.ACTIVE,
    )

    room = relationship("Room", back_populates="discussions")
    topic = relationship("Topic", back_populates="discussions")
    utterance_links = relationship("DecisionUtteranceLink", back_populates="decision")

    __table_args__ = (
        Index("ix_discussions_room_id", "room_id"),
        Index("ix_discussions_topic_id", "topic_id"),
        Index("ix_discussions_status", "status"),
    )


class DecisionUtteranceLink(Base):
    __tablename__ = "decision_utterance_links"

    decision_utterance_link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discussions.discussion_id"),
        nullable=False,
    )

    utterance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("utterances.utterance_id"),
        nullable=False,
    )

    decision = relationship("Discussion", back_populates="utterance_links")
    utterance = relationship("Utterance", back_populates="decision_links")

    __table_args__ = (
        UniqueConstraint(
            "decision_id",
            "utterance_id",
            name="uq_decision_utterance_links_decision_id_utterance_id",
        ),
    )