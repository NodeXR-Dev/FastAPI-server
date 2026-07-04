from datetime import datetime
import json
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.model.graph import SubGraph, Node, Edge, GraphSnapshot, GraphEvent
from app.model.graph import NodeUtteranceLink
from app.model.enum import GraphEventType
from app.schema.graph.response import GraphResponse


class GraphRepository:
    def save_graph_from_response(
        self,
        db: Session,
        room_id: UUID,
        utterance_id: UUID,
        graph: GraphResponse,
    ):
        # 1. 이번 요청으로 생긴 sub_graph 생성
        sub_graph = SubGraph(
            room_id=room_id,
        )
        db.add(sub_graph)
        db.flush()

        node_id_map = {}
        saved_nodes = []

        # 2. 신규 노드 저장
        for node_response in graph.nodes:
            node = Node(
                room_id=room_id,
                sub_graph_id=sub_graph.sub_graph_id,
                parent_node_id=node_response.parent_node_id,
                node_type=node_response.type,
                node_text=node_response.node_text,
                position_x=node_response.position[0] if len(node_response.position) > 0 else None,
                position_y=node_response.position[1] if len(node_response.position) > 1 else None,
                position_z=node_response.position[2] if len(node_response.position) > 2 else None,
            )

            db.add(node)
            db.flush()

            # GraphBuildService에서 만든 임시 node_id → DB에 저장된 실제 node_id 매핑
            node_id_map[node_response.node_id] = node.node_id
            saved_nodes.append(node)

            db.add(
                NodeUtteranceLink(
                    node_id=node.node_id,
                    utterance_id=utterance_id,
                )
            )

        saved_edges = []

        # 3. 신규 엣지 저장
        for edge_response in graph.edges:
            from_node_id = node_id_map.get(
                edge_response.from_node_id,
                edge_response.from_node_id,
            )
            to_node_id = node_id_map.get(
                edge_response.to_node_id,
                edge_response.to_node_id,
            )

            edge = Edge(
                room_id=room_id,
                sub_graph_id=sub_graph.sub_graph_id,
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                label=edge_response.label,
            )

            db.add(edge)
            db.flush()

            saved_edges.append(edge)

        # 4. 전체 그래프 조회
        all_nodes, all_edges = self.find_graph_by_room_id(
            db=db,
            room_id=room_id,
        )

        # 5. 다음 graph version 계산
        next_version = self.get_next_graph_version(
            db=db,
            room_id=room_id,
        )

        # 6. 전체 그래프 기준 snapshot 생성
        snapshot_data = self.build_snapshot_data(
            version=next_version,
            nodes=all_nodes,
            edges=all_edges,
        )

        graph_snapshot = GraphSnapshot(
            room_id=room_id,
            snapshot_data=json.dumps(snapshot_data, ensure_ascii=False),
            version=next_version,
        )

        db.add(graph_snapshot)
        db.flush()

        return sub_graph, graph_snapshot, saved_nodes, saved_edges, all_nodes, all_edges

    def find_graph_by_room_id(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> tuple[list[Node], list[Edge]]:

        nodes = (
            db.query(Node)
            .filter(
                Node.room_id == room_id,
                Node.deleted_at.is_(None),
            )
            .order_by(Node.node_id)
            .all()
        )

        edges = (
            db.query(Edge)
            .filter(
                Edge.room_id == room_id,
                Edge.deleted_at.is_(None),
            )
            .order_by(Edge.edge_id)
            .all()
        )

        return nodes, edges
    def get_next_graph_version(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> int:

        latest_version = (
            db.query(func.max(GraphSnapshot.version))
            .filter(GraphSnapshot.room_id == room_id)
            .scalar()
        )

        if latest_version is None:
            return 1

        return latest_version + 1

    def build_snapshot_data(
        self,
        *,
        version: int,
        nodes: list[Node],
        edges: list[Edge],
    ) -> dict:
        return {
            "graph_version": version,
            "nodes": [
                {
                    "node_id": str(node.node_id),
                    "type": node.node_type.value,
                    "node_text": node.node_text,
                    "position": [
                        node.position_x,
                        node.position_y,
                        node.position_z,
                    ],
                    "parent_node_id": str(node.parent_node_id) if node.parent_node_id else None,
                    "data": {},
                }
                for node in nodes
            ],
            "edges": [
                {
                    "edge_id": str(edge.edge_id),
                    "from_node_id": str(edge.from_node_id),
                    "to_node_id": str(edge.to_node_id),
                    "label": edge.label,
                }
                for edge in edges
            ],
        }
    def find_active_node_by_id(
        self,
        db: Session,
        *,
        room_id: UUID,
        node_id: UUID,
    ) -> Node | None:
        return (
            db.query(Node)
            .filter(
                Node.room_id == room_id,
                Node.node_id == node_id,
                Node.deleted_at.is_(None),
            )
            .first()
        )
    
    def create_sub_graph(
        self,
        *,
        db: Session,
        room_id: UUID,
    ) -> SubGraph:
        sub_graph = SubGraph(
            room_id=room_id,
        )

        db.add(sub_graph)
        db.flush()

        return sub_graph
    
    def create_node(
        self,
        db: Session,
        *,
        room_id: UUID,
        sub_graph_id: UUID | None,
        parent_node_id: UUID | None,
        node_text: str,
        node_type,
        position_x: float | None = None,
        position_y: float | None = None,
        position_z: float | None = None,
    ) -> Node:
        node = Node(
            room_id=room_id,
            sub_graph_id=sub_graph_id,
            parent_node_id=parent_node_id,
            node_type=node_type,
            node_text=node_text,
            position_x=position_x,
            position_y=position_y,
            position_z=position_z,
        )

        db.add(node)
        db.flush()

        return node

    def update_node_position(
        self,
        *,
        node: Node,
        x: float,
        y: float,
        z: float,
    ) -> Node:
        node.position_x = x
        node.position_y = y
        node.position_z = z
        return node

    def update_node_text(
        self,
        *,
        node: Node,
        text: str,
    ) -> Node:
        node.node_text = text
        return node

    def soft_delete_node(
        self,
        *,
        node: Node,
        deleted_at,
    ) -> Node:
        node.deleted_at = deleted_at
        return node
    
    def soft_delete_nodes(
        self,
        *,
        nodes: list[Node],
        deleted_at: datetime,
    ) -> None:
        """
        여러 노드를 soft delete한다.
        """
        for node in nodes:
            node.deleted_at = deleted_at
    
    def find_active_child_nodes_recursively(
        self,
        *,
        db: Session,
        room_id: UUID,
        parent_node_id: UUID,
    ) -> list[Node]:
        """
        특정 부모 노드의 모든 active 자식 노드를 재귀적으로 조회한다.
        - 직접 자식
        - 자식의 자식
        - 그 이하 descendant 전체
        """
        children = (
            db.query(Node)
            .filter(
                Node.room_id == room_id,
                Node.parent_node_id == parent_node_id,
                Node.deleted_at.is_(None),
            )
            .all()
        )

        descendants: list[Node] = []

        for child in children:
            descendants.append(child)

            child_descendants = self.find_active_child_nodes_recursively(
                db=db,
                room_id=room_id,
                parent_node_id=child.node_id,
            )

            descendants.extend(child_descendants)

        return descendants

    def find_active_child_nodes(
        self,
        db: Session,
        *,
        room_id: UUID,
        parent_node_id: UUID,
    ) -> list[Node]:
        return (
            db.query(Node)
            .filter(
                Node.room_id == room_id,
                Node.parent_node_id == parent_node_id,
                Node.deleted_at.is_(None),
            )
            .all()
        )

    # =========================
    # Graph Interaction - Edge
    # =========================

    def find_active_edge_by_id(
        self,
        db: Session,
        *,
        room_id: UUID,
        edge_id: UUID,
    ) -> Edge | None:
        return (
            db.query(Edge)
            .filter(
                Edge.room_id == room_id,
                Edge.edge_id == edge_id,
                Edge.deleted_at.is_(None),
            )
            .first()
        )
    
    def find_active_edges_connected_to_nodes(
        self,
        *,
        db: Session,
        room_id: UUID,
        node_ids: list[UUID],
    ) -> list[Edge]:
        """
        여러 노드 중 하나라도 연결된 active edge를 조회한다.
        기존 find_active_edges_connected_to_node()를 재사용한다.
        """
        edge_map: dict[UUID, Edge] = {}

        for node_id in node_ids:
            connected_edges = self.find_active_edges_connected_to_node(
                db=db,
                room_id=room_id,
                node_id=node_id,
            )

            for edge in connected_edges:
                edge_map[edge.edge_id] = edge

        return list(edge_map.values())

    def find_active_edge_between_nodes(
        self,
        db: Session,
        *,
        room_id: UUID,
        from_node_id: UUID,
        to_node_id: UUID,
    ) -> Edge | None:
        return (
            db.query(Edge)
            .filter(
                Edge.room_id == room_id,
                Edge.from_node_id == from_node_id,
                Edge.to_node_id == to_node_id,
                Edge.deleted_at.is_(None),
            )
            .first()
        )

    def find_active_edges_connected_to_node(
        self,
        db: Session,
        *,
        room_id: UUID,
        node_id: UUID,
    ) -> list[Edge]:
        return (
            db.query(Edge)
            .filter(
                Edge.room_id == room_id,
                Edge.deleted_at.is_(None),
                or_(
                    Edge.from_node_id == node_id,
                    Edge.to_node_id == node_id,
                ),
            )
            .all()
        )

    def create_edge(
        self,
        db: Session,
        *,
        room_id: UUID,
        sub_graph_id: UUID | None,
        from_node_id: UUID,
        to_node_id: UUID,
    ) -> Edge:
        edge = Edge(
            room_id=room_id,
            sub_graph_id=sub_graph_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
        )

        db.add(edge)
        db.flush()

        return edge

    def soft_delete_edge(
        self,
        *,
        edge: Edge,
        deleted_at,
    ) -> Edge:
        edge.deleted_at = deleted_at
        return edge

    def soft_delete_edges(
        self,
        *,
        edges: list[Edge],
        deleted_at,
    ) -> list[Edge]:
        for edge in edges:
            edge.deleted_at = deleted_at

        return edges

    # =========================
    # Graph Interaction - Event
    # =========================

    def create_graph_event(
        self,
        db: Session,
        *,
        room_id: UUID,
        user_id: UUID | None,
        event_type: GraphEventType,
        payload: dict,
        node_id: UUID | None = None,
        edge_id: UUID | None = None,
    ) -> GraphEvent:
        graph_event = GraphEvent(
            room_id=room_id,
            user_id=user_id,
            node_id=node_id,
            edge_id=edge_id,
            event_type=event_type,
            payload=json.dumps(payload, ensure_ascii=False, default=str),
        )

        db.add(graph_event)
        db.flush()

        return graph_event

    # =========================
    # Graph Interaction - Snapshot
    # =========================

    def create_graph_snapshot_from_current_graph(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> GraphSnapshot:
        all_nodes, all_edges = self.find_graph_by_room_id(
            db=db,
            room_id=room_id,
        )

        next_version = self.get_next_graph_version(
            db=db,
            room_id=room_id,
        )

        snapshot_data = self.build_snapshot_data(
            version=next_version,
            nodes=all_nodes,
            edges=all_edges,
        )

        graph_snapshot = GraphSnapshot(
            room_id=room_id,
            snapshot_data=json.dumps(snapshot_data, ensure_ascii=False),
            version=next_version,
        )

        db.add(graph_snapshot)
        db.flush()

        return graph_snapshot
    
    # =========================
    # 2D Generation Prompt
    # =========================

    def find_active_ancestor_chain_to_root(
        self,
        db: Session,
        *,
        room_id: UUID,
        node_id: UUID,
    ) -> list[Node]:
        """
        node_id에서 시작해서 parent_node_id를 따라 root node까지 올라간다.
        반환 순서는 root -> target node.
        """
        current = self.find_active_node_by_id(
            db=db,
            room_id=room_id,
            node_id=node_id,
        )

        if current is None:
            raise ValueError(f"활성 노드를 찾을 수 없습니다. node_id={node_id}")

        chain: list[Node] = []
        visited_node_ids: set[UUID] = set()

        while current is not None:
            if current.node_id in visited_node_ids:
                raise ValueError(
                    f"노드 부모 체인에서 cycle이 감지되었습니다. node_id={current.node_id}"
                )

            visited_node_ids.add(current.node_id)
            chain.append(current)

            if current.parent_node_id is None:
                break

            current = self.find_active_node_by_id(
                db=db,
                room_id=room_id,
                node_id=current.parent_node_id,
            )

            if current is None:
                break

        chain.reverse()
        return chain