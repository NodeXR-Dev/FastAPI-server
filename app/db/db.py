import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


room_member_role_enum = ENUM(name="room_member_role", create_type=False)
room_member_state_enum = ENUM(name="room_member_state", create_type=False)
topic_status_enum = ENUM(name="topic_status", create_type=False)
episode_status_enum = ENUM(name="episode_status", create_type=False)
decision_status_enum = ENUM(name="decision_status", create_type=False)
issue_status_enum = ENUM(name="issue_status", create_type=False)
conflict_status_enum = ENUM(name="conflict_status", create_type=False)
node_type_enum = ENUM(name="node_type", create_type=False)
edge_type_enum = ENUM(name="edge_type", create_type=False)
asset_type_enum = ENUM(name="asset_type", create_type=False)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)


class Room(Base):
    __tablename__ = "rooms"

    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    room_password_hash: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class RoomMember(Base):
    __tablename__ = "room_members"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id"),
    )

    room_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    role: Mapped[str] = mapped_column(room_member_role_enum, nullable=False)
    state: Mapped[str] = mapped_column(room_member_state_enum, nullable=False)


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        Index("ix_topics_room_id", "room_id"),
        Index("ix_topics_room_id_status", "room_id", "status"),
    )

    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(topic_status_enum, nullable=False, server_default=text("'ACTIVE'"))
    centroid_embedding: Mapped[list[float] | None] = mapped_column(Vector())
    last_activity_at: Mapped[object | None] = mapped_column(DateTime)


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        Index("ix_episodes_room_id", "room_id"),
        Index("ix_episodes_topic_id", "topic_id"),
    )

    episode_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.topic_id"), nullable=False)
    status: Mapped[str] = mapped_column(episode_status_enum, nullable=False, server_default=text("'OPEN'"))
    summary_text: Mapped[str | None] = mapped_column(Text)
    decisions_summary: Mapped[str | None] = mapped_column(Text)
    constraints_summary: Mapped[str | None] = mapped_column(Text)
    issues_summary: Mapped[str | None] = mapped_column(Text)
    conflicts_summary: Mapped[str | None] = mapped_column(Text)


class Utterance(Base):
    __tablename__ = "utterances"
    __table_args__ = (
        Index("ix_utterances_room_id", "room_id"),
        Index("ix_utterances_episode_id", "episode_id"),
    )

    utterance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    episode_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("episodes.episode_id"), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector())


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        Index("ix_decisions_room_id", "room_id"),
        Index("ix_decisions_topic_id", "topic_id"),
        Index("ix_decisions_status", "status"),
    )

    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.topic_id"), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(decision_status_enum, nullable=False, server_default=text("'PROPOSED'"))


class DecisionUtteranceLink(Base):
    __tablename__ = "decision_utterance_links"
    __table_args__ = (
        UniqueConstraint("decision_id", "utterance_id"),
    )

    decision_utterance_link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("decisions.decision_id"), nullable=False)
    utterance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utterances.utterance_id"), nullable=False)


class Constraint(Base):
    __tablename__ = "constraints"
    __table_args__ = (
        Index("ix_constraints_room_id", "room_id"),
        Index("ix_constraints_topic_id", "topic_id"),
    )

    constraint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.topic_id"), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)


class ConstraintUtteranceLink(Base):
    __tablename__ = "constraint_utterance_links"
    __table_args__ = (
        UniqueConstraint("constraint_id", "utterance_id"),
    )

    constraint_utterance_link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    constraint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("constraints.constraint_id"), nullable=False)
    utterance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utterances.utterance_id"), nullable=False)


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        Index("ix_issues_room_id", "room_id"),
        Index("ix_issues_topic_id", "topic_id"),
        Index("ix_issues_status", "status"),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.topic_id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(issue_status_enum, nullable=False, server_default=text("'OPEN'"))


class IssueUtteranceLink(Base):
    __tablename__ = "issue_utterance_links"
    __table_args__ = (
        UniqueConstraint("issue_id", "utterance_id"),
    )

    issue_utterance_link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("issues.issue_id"), nullable=False)
    utterance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utterances.utterance_id"), nullable=False)


class Conflict(Base):
    __tablename__ = "conflicts"
    __table_args__ = (
        Index("ix_conflicts_room_id", "room_id"),
        Index("ix_conflicts_topic_id", "topic_id"),
    )

    conflict_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.topic_id"), nullable=False)
    conflict_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(conflict_status_enum, nullable=False, server_default=text("'SUSPECTED'"))


class ConflictUtteranceLink(Base):
    __tablename__ = "conflict_utterance_links"
    __table_args__ = (
        UniqueConstraint("conflict_id", "utterance_id"),
    )

    conflict_utterance_link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    conflict_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conflicts.conflict_id"), nullable=False)
    utterance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utterances.utterance_id"), nullable=False)


class SubGraph(Base):
    __tablename__ = "sub_graphs"

    sub_graph_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.topic_id"))


class Node(Base):
    __tablename__ = "nodes"
    __table_args__ = (
        Index("ix_nodes_room_id", "room_id"),
        Index("ix_nodes_sub_graph_id", "sub_graph_id"),
    )

    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    sub_graph_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sub_graphs.sub_graph_id"))
    parent_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("nodes.node_id"))
    node_type: Mapped[str] = mapped_column(node_type_enum, nullable=False)
    node_text: Mapped[str] = mapped_column(String, nullable=False)
    position_x: Mapped[float | None] = mapped_column(Double)
    position_y: Mapped[float | None] = mapped_column(Double)
    position_z: Mapped[float | None] = mapped_column(Double)


class NodeUtteranceLink(Base):
    __tablename__ = "node_utterance_links"
    __table_args__ = (
        UniqueConstraint("node_id", "utterance_id"),
    )

    node_utterance_link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("nodes.node_id"), nullable=False)
    utterance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utterances.utterance_id"), nullable=False)


class Edge(Base):
    __tablename__ = "edges"

    edge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    sub_graph_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sub_graphs.sub_graph_id"))
    from_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("nodes.node_id"), nullable=False)
    to_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("nodes.node_id"), nullable=False)
    edge_type: Mapped[str] = mapped_column(edge_type_enum, nullable=False)


class PartNode(Base):
    __tablename__ = "part_nodes"

    part_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    part_name: Mapped[str] = mapped_column(String, nullable=False)


class PartNodeNodeLink(Base):
    __tablename__ = "part_node_node_links"
    __table_args__ = (
        UniqueConstraint("part_node_id", "node_id"),
    )

    part_node_node_link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    part_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("part_nodes.part_node_id"), nullable=False)
    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("nodes.node_id"), nullable=False)


class GraphSnapshot(Base):
    __tablename__ = "graph_snapshots"

    graph_snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    snapshot_data: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[object | None] = mapped_column(DateTime)


class Asset(Base):
    __tablename__ = "assets"

    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    graph_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("graph_snapshots.graph_snapshot_id"))
    asset_type: Mapped[str] = mapped_column(asset_type_enum, nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_text: Mapped[str | None] = mapped_column(Text)


class Reference(Base):
    __tablename__ = "references"

    reference_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("nodes.node_id"))
    query_text: Mapped[str | None] = mapped_column(String)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[object | None] = mapped_column(DateTime)