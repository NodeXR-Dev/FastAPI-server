import uuid
from datetime import datetime

from sqlalchemy import DateTime, Double, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import NodeType


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

    room = relationship("Room", back_populates="sub_graphs")
    nodes = relationship("Node", back_populates="sub_graph")
    edges = relationship("Edge", back_populates="sub_graph")


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
        nullable=True,
    )

    parent_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nodes.node_id"),
        nullable=True,
    )

    node_type: Mapped[NodeType] = mapped_column(
        Enum(NodeType),
        nullable=False,
    )

    node_text: Mapped[str] = mapped_column(String, nullable=False)

    position_x: Mapped[float | None] = mapped_column(Double, nullable=True)
    position_y: Mapped[float | None] = mapped_column(Double, nullable=True)
    position_z: Mapped[float | None] = mapped_column(Double, nullable=True)

    room = relationship("Room", back_populates="nodes")
    sub_graph = relationship("SubGraph", back_populates="nodes")

    parent_node = relationship(
        "Node",
        remote_side=[node_id],
        back_populates="child_nodes",
    )

    child_nodes = relationship(
        "Node",
        back_populates="parent_node",
    )

    utterance_links = relationship("NodeUtteranceLink", back_populates="node")
    references = relationship("Reference", back_populates="node")

    outgoing_edges = relationship(
        "Edge",
        foreign_keys="Edge.from_node_id",
        back_populates="from_node",
    )

    incoming_edges = relationship(
        "Edge",
        foreign_keys="Edge.to_node_id",
        back_populates="to_node",
    )

    __table_args__ = (
        Index("ix_nodes_room_id", "room_id"),
        Index("ix_nodes_sub_graph_id", "sub_graph_id"),
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

    node = relationship("Node", back_populates="utterance_links")
    utterance = relationship("Utterance", back_populates="node_links")

    __table_args__ = (
        UniqueConstraint(
            "node_id",
            "utterance_id",
            name="uq_node_utterance_links_node_id_utterance_id",
        ),
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
        nullable=True,
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

    label: Mapped[str] = mapped_column(String, nullable=False)

    room = relationship("Room", back_populates="edges")
    sub_graph = relationship("SubGraph", back_populates="edges")

    from_node = relationship(
        "Node",
        foreign_keys=[from_node_id],
        back_populates="outgoing_edges",
    )

    to_node = relationship(
        "Node",
        foreign_keys=[to_node_id],
        back_populates="incoming_edges",
    )

    __table_args__ = (
        Index("ix_edges_room_id", "room_id"),
        Index("ix_edges_sub_graph_id", "sub_graph_id"),
        Index("ix_edges_from_node_id", "from_node_id"),
        Index("ix_edges_to_node_id", "to_node_id"),
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
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    room = relationship("Room", back_populates="graph_snapshots")
    assets = relationship("Asset", back_populates="graph_snapshot")

    __table_args__ = (
        Index("ix_graph_snapshots_room_id", "room_id"),
    )