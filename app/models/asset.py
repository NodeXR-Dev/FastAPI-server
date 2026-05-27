import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AssetType


class Asset(Base):
    __tablename__ = "assets"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    graph_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_snapshots.graph_snapshot_id"),
        nullable=True,
    )

    asset_type: Mapped[AssetType] = mapped_column(
        Enum(AssetType),
        nullable=False,
    )

    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    room = relationship("Room", back_populates="assets")
    graph_snapshot = relationship("GraphSnapshot", back_populates="assets")

    __table_args__ = (
        Index("ix_assets_room_id", "room_id"),
        Index("ix_assets_graph_snapshot_id", "graph_snapshot_id"),
    )


class Reference(Base):
    __tablename__ = "references"

    reference_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nodes.node_id"),
        nullable=True,
    )

    query_text: Mapped[str | None] = mapped_column(String, nullable=True)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)

    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    room = relationship("Room", back_populates="references")
    node = relationship("Node", back_populates="references")

    __table_args__ = (
        Index("ix_references_room_id", "room_id"),
        Index("ix_references_node_id", "node_id"),
    )