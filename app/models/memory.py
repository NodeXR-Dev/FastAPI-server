# app/models/memory.py

import uuid

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.models.base import Base
from app.models.enums import (
    AlertStatus,
    AlertType,
    DesignFactLinkType,
    DesignFactStatus,
    DesignFactType,
    DesignFactUtteranceLinkRole,
    MemoryStatus,
    SemanticMemoryType,
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
    )

    memory_type: Mapped[SemanticMemoryType] = mapped_column(
        Enum(SemanticMemoryType, name="semantic_memory_type"),
        nullable=False,
    )

    status: Mapped[MemoryStatus] = mapped_column(
        Enum(MemoryStatus, name="memory_status"),
        nullable=False,
        default=MemoryStatus.ACTIVE,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(768))

    target_scope: Mapped[str | None] = mapped_column(String)
    design_dimension: Mapped[str | None] = mapped_column(String)

    time_window_start: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    time_window_end: Mapped[object | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    design_facts: Mapped[list["DesignFact"]] = relationship(
        back_populates="semantic_memory",
    )

    __table_args__ = (
        Index("ix_semantic_memories_room_id", "room_id"),
        Index("ix_semantic_memories_topic_id", "topic_id"),
        Index("ix_semantic_memories_memory_type", "memory_type"),
        Index("ix_semantic_memories_status", "status"),
        Index("ix_semantic_memories_target_scope", "target_scope"),
        Index("ix_semantic_memories_design_dimension", "design_dimension"),
        Index("ix_semantic_memories_time_window_start", "time_window_start"),
        Index("ix_semantic_memories_time_window_end", "time_window_end"),
        Index("ix_semantic_memories_created_at", "created_at"),
        Index(
            "ix_semantic_memories_room_type_status",
            "room_id",
            "memory_type",
            "status",
        ),
        Index(
            "ix_semantic_memories_room_scope_dimension",
            "room_id",
            "target_scope",
            "design_dimension",
        ),
    )


class DesignFact(Base):
    __tablename__ = "design_facts"

    design_fact_id: Mapped[uuid.UUID] = mapped_column(
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
    )

    semantic_memory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("semantic_memories.semantic_memory_id"),
    )

    target_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nodes.node_id"),
    )

    fact_type: Mapped[DesignFactType] = mapped_column(
        Enum(DesignFactType, name="design_fact_type"),
        nullable=False,
    )

    status: Mapped[DesignFactStatus] = mapped_column(
        Enum(DesignFactStatus, name="design_fact_status"),
        nullable=False,
        default=DesignFactStatus.CANDIDATE,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(768))

    target_scope: Mapped[str | None] = mapped_column(String)
    design_dimension: Mapped[str | None] = mapped_column(String)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
    )

    semantic_memory: Mapped["SemanticMemory | None"] = relationship(
        back_populates="design_facts",
    )

    utterance_links: Mapped[list["DesignFactUtteranceLink"]] = relationship(
        back_populates="design_fact",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_design_facts_room_id", "room_id"),
        Index("ix_design_facts_topic_id", "topic_id"),
        Index("ix_design_facts_semantic_memory_id", "semantic_memory_id"),
        Index("ix_design_facts_target_node_id", "target_node_id"),
        Index("ix_design_facts_fact_type", "fact_type"),
        Index("ix_design_facts_status", "status"),
        Index("ix_design_facts_target_scope", "target_scope"),
        Index("ix_design_facts_design_dimension", "design_dimension"),
        Index("ix_design_facts_created_at", "created_at"),
        Index("ix_design_facts_room_type_status", "room_id", "fact_type", "status"),
        Index(
            "ix_design_facts_room_scope_dimension",
            "room_id",
            "target_scope",
            "design_dimension",
        ),
    )


class DesignFactLink(Base):
    __tablename__ = "design_fact_links"

    design_fact_link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    from_fact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("design_facts.design_fact_id"),
        nullable=False,
    )

    to_fact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("design_facts.design_fact_id"),
        nullable=False,
    )

    link_type: Mapped[DesignFactLinkType] = mapped_column(
        Enum(DesignFactLinkType, name="design_fact_link_type"),
        nullable=False,
    )

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    from_fact: Mapped["DesignFact"] = relationship(
        foreign_keys=[from_fact_id],
    )

    to_fact: Mapped["DesignFact"] = relationship(
        foreign_keys=[to_fact_id],
    )

    __table_args__ = (
        UniqueConstraint(
            "from_fact_id",
            "to_fact_id",
            "link_type",
            name="uq_design_fact_links_from_to_type",
        ),
        Index("ix_design_fact_links_room_id", "room_id"),
        Index("ix_design_fact_links_from_fact_id", "from_fact_id"),
        Index("ix_design_fact_links_to_fact_id", "to_fact_id"),
        Index("ix_design_fact_links_link_type", "link_type"),
    )


class DesignFactUtteranceLink(Base):
    __tablename__ = "design_fact_utterance_links"

    design_fact_utterance_link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    design_fact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("design_facts.design_fact_id"),
        nullable=False,
    )

    utterance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("utterances.utterance_id"),
        nullable=False,
    )

    link_role: Mapped[DesignFactUtteranceLinkRole] = mapped_column(
        Enum(
            DesignFactUtteranceLinkRole,
            name="design_fact_utterance_link_role",
        ),
        nullable=False,
        default=DesignFactUtteranceLinkRole.SOURCE,
    )

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    design_fact: Mapped["DesignFact"] = relationship(
        back_populates="utterance_links",
    )

    __table_args__ = (
        UniqueConstraint(
            "design_fact_id",
            "utterance_id",
            "link_role",
            name="uq_design_fact_utterance_links_fact_utterance_role",
        ),
        Index("ix_design_fact_utterance_links_design_fact_id", "design_fact_id"),
        Index("ix_design_fact_utterance_links_utterance_id", "utterance_id"),
        Index("ix_design_fact_utterance_links_link_role", "link_role"),
    )


class AgentAlert(Base):
    __tablename__ = "agent_alerts"

    agent_alert_id: Mapped[uuid.UUID] = mapped_column(
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
    )

    triggering_utterance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("utterances.utterance_id"),
    )

    related_fact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("design_facts.design_fact_id"),
    )

    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType, name="alert_type"),
        nullable=False,
    )

    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, name="alert_status"),
        nullable=False,
        default=AlertStatus.PENDING,
    )

    message: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_agent_alerts_room_id", "room_id"),
        Index("ix_agent_alerts_topic_id", "topic_id"),
        Index("ix_agent_alerts_triggering_utterance_id", "triggering_utterance_id"),
        Index("ix_agent_alerts_related_fact_id", "related_fact_id"),
        Index("ix_agent_alerts_alert_type", "alert_type"),
        Index("ix_agent_alerts_status", "status"),
        Index("ix_agent_alerts_created_at", "created_at"),
    )