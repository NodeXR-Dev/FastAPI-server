import uuid

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.model.enum import GraphEventType, NodeType


class SubGraph(Base):
    __tablename__ = "sub_graphs"

    sub_graph_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    nodes: Mapped[list["Node"]] = relationship(
        back_populates="sub_graph",
    )

    edges: Mapped[list["Edge"]] = relationship(
        back_populates="sub_graph",
    )

    __table_args__ = (
        Index("ix_sub_graphs_room_id", "room_id"),
    )


class Node(Base):
    __tablename__ = "nodes"

    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    sub_graph_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sub_graphs.sub_graph_id"),
    )

    parent_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nodes.node_id"),
    )

    node_type: Mapped[NodeType] = mapped_column(
        Enum(NodeType, name="node_type"),
        nullable=False,
    )

    node_text: Mapped[str] = mapped_column(String, nullable=False)

    position_x: Mapped[float | None] = mapped_column(Float)
    position_y: Mapped[float | None] = mapped_column(Float)
    position_z: Mapped[float | None] = mapped_column(Float)
    
    deleted_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    sub_graph: Mapped["SubGraph | None"] = relationship(
        back_populates="nodes",
    )

    parent: Mapped["Node | None"] = relationship(
        remote_side=[node_id],
        back_populates="children",
    )

    children: Mapped[list["Node"]] = relationship(
        back_populates="parent",
    )

    utterance_links: Mapped[list["NodeUtteranceLink"]] = relationship(
        back_populates="node",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_nodes_room_id", "room_id"),
        Index("ix_nodes_sub_graph_id", "sub_graph_id"),
        Index("ix_nodes_parent_node_id", "parent_node_id"),
    )


class Edge(Base):
    __tablename__ = "edges"

    edge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    sub_graph_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sub_graphs.sub_graph_id"),
    )

    from_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nodes.node_id"),
        nullable=False,
    )

    to_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nodes.node_id"),
        nullable=False,
    )

    label: Mapped[str] = mapped_column(String, nullable=True)
    
    deleted_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    sub_graph: Mapped["SubGraph | None"] = relationship(
        back_populates="edges",
    )

    from_node: Mapped["Node"] = relationship(
        foreign_keys=[from_node_id],
    )

    to_node: Mapped["Node"] = relationship(
        foreign_keys=[to_node_id],
    )

    __table_args__ = (
        Index("ix_edges_room_id", "room_id"),
        Index("ix_edges_sub_graph_id", "sub_graph_id"),
        Index("ix_edges_from_node_id", "from_node_id"),
        Index("ix_edges_to_node_id", "to_node_id"),
    )


class NodeUtteranceLink(Base):
    __tablename__ = "node_utterance_links"

    node_utterance_link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nodes.node_id"),
        nullable=False,
    )

    utterance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("utterances.utterance_id"),
        nullable=False,
    )

    node: Mapped["Node"] = relationship(
        back_populates="utterance_links",
    )

    __table_args__ = (
        UniqueConstraint(
            "node_id",
            "utterance_id",
            name="uq_node_utterance_links_node_utterance",
        ),
        Index("ix_node_utterance_links_node_id", "node_id"),
        Index("ix_node_utterance_links_utterance_id", "utterance_id"),
    )


class GraphEvent(Base):
    __tablename__ = "graph_events"

    graph_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id"),
    )

    node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nodes.node_id"),
    )

    edge_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("edges.edge_id"),
    )

    related_fact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("design_facts.design_fact_id"),
    )

    event_type: Mapped[GraphEventType] = mapped_column(
        Enum(GraphEventType, name="graph_event_type"),
        nullable=False,
    )

    payload: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_graph_events_room_id", "room_id"),
        Index("ix_graph_events_user_id", "user_id"),
        Index("ix_graph_events_node_id", "node_id"),
        Index("ix_graph_events_edge_id", "edge_id"),
        Index("ix_graph_events_related_fact_id", "related_fact_id"),
        Index("ix_graph_events_event_type", "event_type"),
        Index("ix_graph_events_created_at", "created_at"),
    )


class GraphSnapshot(Base):
    __tablename__ = "graph_snapshots"

    graph_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    snapshot_data: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_graph_snapshots_room_id", "room_id"),
    )


class Feature(Base):
    __tablename__ = "features"

    feature_id: Mapped[uuid.UUID] = mapped_column(
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