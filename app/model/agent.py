import uuid

from sqlalchemy import UUID, DateTime, Enum, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base
from app.model.enum import AlertStatus, AlertType
from sqlalchemy.dialects.postgresql import UUID


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