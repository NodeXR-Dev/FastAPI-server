from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.model.graph import Edge, Node, SubGraph


class GraphRestoreRepository:
    """Read-only queries for reconstructing the Unity room graph."""

    def find_non_deleted_sub_graphs_by_room_id(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> list[SubGraph]:
        stmt = (
            select(SubGraph)
            .where(
                SubGraph.room_id == room_id,
                SubGraph.deleted_at.is_(None),
            )
            .order_by(SubGraph.sub_graph_id.asc())
        )
        return list(db.scalars(stmt).all())

    def find_non_deleted_nodes_by_sub_graph_ids(
        self,
        db: Session,
        *,
        room_id: UUID,
        sub_graph_ids: list[UUID],
    ) -> list[Node]:
        if not sub_graph_ids:
            return []

        stmt = (
            select(Node)
            .where(
                Node.room_id == room_id,
                Node.sub_graph_id.in_(sub_graph_ids),
                Node.deleted_at.is_(None),
            )
            .order_by(Node.sub_graph_id.asc(), Node.node_id.asc())
        )
        return list(db.scalars(stmt).all())

    def find_non_deleted_edges_by_sub_graph_ids(
        self,
        db: Session,
        *,
        room_id: UUID,
        sub_graph_ids: list[UUID],
    ) -> list[Edge]:
        if not sub_graph_ids:
            return []

        stmt = (
            select(Edge)
            .where(
                Edge.room_id == room_id,
                Edge.deleted_at.is_(None),
                or_(
                    Edge.sub_graph_id.in_(sub_graph_ids),
                    Edge.sub_graph_id.is_(None),
                ),
            )
            .order_by(Edge.sub_graph_id.asc(), Edge.edge_id.asc())
        )
        return list(db.scalars(stmt).all())
