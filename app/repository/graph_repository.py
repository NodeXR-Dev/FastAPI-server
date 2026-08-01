from collections import defaultdict
from datetime import datetime
import json
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.model.graph import SubGraph, Node, Edge, GraphSnapshot, GraphEvent
from app.model.reference import Reference
from app.model.memory import NodeUtteranceLink
from app.model.enum import GraphEventType, NodeType
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
        sub_graph = self.create_sub_graph(
            db=db,
            room_id=room_id,
        )

        node_id_map = {}
        saved_nodes = []

        # 2. 신규 노드 저장
        for node_response in graph.nodes:
            node = self.create_node(
                db=db,
                room_id=room_id,
                sub_graph_id=sub_graph.sub_graph_id,
                parent_node_id=node_response.parent_node_id,
                node_type=node_response.type,
                node_text=node_response.node_text,
                position_x=node_response.position[0] if len(node_response.position) > 0 else None,
                position_y=node_response.position[1] if len(node_response.position) > 1 else None,
                position_z=node_response.position[2] if len(node_response.position) > 2 else None,
            )

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

            edge = self.create_edge(
                db=db,
                room_id=room_id,
                sub_graph_id=sub_graph.sub_graph_id,
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                label=edge_response.label,
            )

            saved_edges.append(edge)

        # 4. 전체 그래프 기준 snapshot 생성
        graph_snapshot = self.create_graph_snapshot_from_current_graph(
            db=db,
            room_id=room_id,
        )

        # 5. 반환용 전체 그래프 조회
        all_nodes, all_edges = self.find_graph_by_room_id(
            db=db,
            room_id=room_id,
        )

        return sub_graph, graph_snapshot, saved_nodes, saved_edges, all_nodes, all_edges

    def find_graph_by_room_id(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> tuple[list[Node], list[Edge]]:
        """
        현재 그래프 조회용.
        deleted_at이 null인 active node/edge만 반환한다.
        """
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

    def get_latest_graph_version(
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

        return latest_version or 0

    def get_next_graph_version(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> int:
        return self.get_latest_graph_version(
            db=db,
            room_id=room_id,
        ) + 1

    def build_snapshot_data(
        self,
        *,
        version: int,
        nodes: list[Node],
        edges: list[Edge],
        core_2d_image: dict | None = None,
        reference_by_node_id: dict[UUID, Reference] | None = None,
        generation_context: dict | None = None,
    ) -> dict:
        """
        GraphSnapshot.snapshot_data에 저장할 JSON dict를 만든다.

        규칙
        - nodes/edges는 이미 active(deleted_at is null) 데이터만 전달받는다고 가정한다.
        - snapshot_data는 GraphSnapshotResponse 형태에 맞춘다.
        - DB의 Edge.from_node_id/to_node_id는 변경하지 않는다.
        - snapshot_data를 만들 때만 PART -> PROPERTY edge의 to_node_id를
          PROPERTY가 속한 sub_graph의 root_node_id로 변환한다.
        - used_in_generation은 active PART -> PROPERTY edge를 기준으로 재계산한다.
          PART, 연결된 PROPERTY, PROPERTY의 parent_node_id ancestor chain,
          그리고 그 경로의 edge들을 true로 표시한다.
        - 직전 정책 보완 사항에 따라 PART/PROPERTY -> REFERENCE 직접 연결도 true로 표시한다.
        """
        reference_by_node_id = reference_by_node_id or {}
        node_by_id = {
            node.node_id: node
            for node in nodes
        }
        active_edges = [
            edge
            for edge in edges
            if edge.from_node_id in node_by_id and edge.to_node_id in node_by_id
        ]
        active_edge_by_parent_child = self._build_active_edge_by_parent_child(
            edges=active_edges,
        )

        used_node_ids, used_edge_ids = self._resolve_used_in_generation(
            nodes=nodes,
            edges=active_edges,
        )
        attached_part_node_ids = {
            edge.from_node_id
            for edge in active_edges
            if self._is_part_property_edge(
                from_node=node_by_id[edge.from_node_id],
                to_node=node_by_id[edge.to_node_id],
            )
        }

        nodes_by_sub_graph_id: dict[UUID, list[Node]] = defaultdict(list)
        edges_by_sub_graph_id: dict[UUID, list[Edge]] = defaultdict(list)

        for node in nodes:
            if node.sub_graph_id is None:
                continue
            nodes_by_sub_graph_id[node.sub_graph_id].append(node)

        for edge in active_edges:
            sub_graph_id = edge.sub_graph_id

            if sub_graph_id is None:
                from_node = node_by_id.get(edge.from_node_id)
                sub_graph_id = from_node.sub_graph_id if from_node is not None else None

            if sub_graph_id is None:
                continue

            edges_by_sub_graph_id[sub_graph_id].append(edge)

        sub_graph_ids = sorted(
            set(nodes_by_sub_graph_id.keys()) | set(edges_by_sub_graph_id.keys()),
            key=str,
        )

        snapshot_data = {
            "graph_version": version,
            "core_2d_image": self._build_core_2d_image_snapshot(
                core_2d_image=core_2d_image,
            ),
            "sub_graphs": [
                {
                    "sub_graph_id": str(sub_graph_id),
                    "root_node_id": self._resolve_root_node_id(
                        nodes=nodes_by_sub_graph_id.get(sub_graph_id, []),
                        excluded_root_node_ids=attached_part_node_ids,
                    ),
                    "nodes": [
                        self._build_node_snapshot(
                            node=node,
                            used_in_generation=node.node_id in used_node_ids,
                            reference=reference_by_node_id.get(node.node_id),
                        )
                        for node in sorted(
                            nodes_by_sub_graph_id.get(sub_graph_id, []),
                            key=lambda item: str(item.node_id),
                        )
                    ],
                    "edges": [
                        self._build_edge_snapshot(
                            edge=edge,
                            node_by_id=node_by_id,
                            active_edge_by_parent_child=active_edge_by_parent_child,
                            used_in_generation=edge.edge_id in used_edge_ids,
                        )
                        for edge in sorted(
                            edges_by_sub_graph_id.get(sub_graph_id, []),
                            key=lambda item: str(item.edge_id),
                        )
                    ],
                }
                for sub_graph_id in sub_graph_ids
            ],
        }
        if generation_context is not None:
            snapshot_data["_generation_context"] = json.loads(
                json.dumps(generation_context, ensure_ascii=False, default=str),
            )

        return snapshot_data

    def _resolve_used_in_generation(
        self,
        *,
        nodes: list[Node],
        edges: list[Edge],
    ) -> tuple[set[UUID], set[UUID]]:
        """
        active edge 전체를 기준으로 snapshot의 used_in_generation을 재계산한다.

        핵심 정책
        - PART -> PROPERTY edge가 active이면:
          1) PART node true
          2) PART -> PROPERTY edge true
          3) PROPERTY node true
          4) PROPERTY에서 parent_node_id를 따라 root까지 모든 ancestor node true
          5) 해당 ancestor chain에 존재하는 parent-child edge true
        - edge 삭제 시에는 deleted_at이 null인 active edge 목록에서 빠지므로
          별도 DB 컬럼 없이 snapshot 재계산 결과에서 false가 된다.
        - edge label은 관계 표현용이므로 used 판단에 사용하지 않는다.
        - REFERENCE는 직전 정책 보완에 따라 PART/PROPERTY에서 직접 연결된 경우 true 처리한다.
        """
        node_by_id = {
            node.node_id: node
            for node in nodes
        }
        active_edge_by_parent_child = self._build_active_edge_by_parent_child(
            edges=edges,
        )

        used_node_ids: set[UUID] = set()
        used_edge_ids: set[UUID] = set()

        for edge in edges:
            from_node = node_by_id.get(edge.from_node_id)
            to_node = node_by_id.get(edge.to_node_id)

            if from_node is None or to_node is None:
                continue

            if self._is_part_property_edge(
                from_node=from_node,
                to_node=to_node,
            ):
                used_node_ids.add(from_node.node_id)
                used_node_ids.add(to_node.node_id)
                used_edge_ids.add(edge.edge_id)

                ancestor_node_ids, ancestor_edge_ids = self._collect_ancestor_path_to_root(
                    node=to_node,
                    node_by_id=node_by_id,
                    active_edge_by_parent_child=active_edge_by_parent_child,
                )
                used_node_ids.update(ancestor_node_ids)
                used_edge_ids.update(ancestor_edge_ids)
                continue

            if self._is_reference_generation_edge(
                from_node=from_node,
                to_node=to_node,
            ):
                used_node_ids.add(from_node.node_id)
                used_node_ids.add(to_node.node_id)
                used_edge_ids.add(edge.edge_id)

        return used_node_ids, used_edge_ids

    def _is_part_property_edge(
        self,
        *,
        from_node: Node,
        to_node: Node,
    ) -> bool:
        return (
            self._node_type_value(from_node) == NodeType.PART.value
            and self._node_type_value(to_node) == NodeType.PROPERTY.value
        )

    def _is_reference_generation_edge(
        self,
        *,
        from_node: Node,
        to_node: Node,
    ) -> bool:
        return (
            self._node_type_value(from_node)
            in {
                NodeType.PART.value,
                NodeType.PROPERTY.value,
            }
            and self._node_type_value(to_node) == NodeType.REFERENCE.value
        )

    def _build_active_edge_by_parent_child(
        self,
        *,
        edges: list[Edge],
    ) -> dict[tuple[UUID, UUID], Edge]:
        edge_by_parent_child: dict[tuple[UUID, UUID], Edge] = {}

        for edge in edges:
            edge_by_parent_child[(edge.from_node_id, edge.to_node_id)] = edge

        return edge_by_parent_child

    def _collect_ancestor_path_to_root(
        self,
        *,
        node: Node,
        node_by_id: dict[UUID, Node],
        active_edge_by_parent_child: dict[tuple[UUID, UUID], Edge],
    ) -> tuple[set[UUID], set[UUID]]:
        """
        node에서 parent_node_id를 따라 root까지 올라가며 node와 edge를 수집한다.
        parent-child edge는 보통 parent -> child 방향이지만, 혹시 반대로 저장된 edge도
        놓치지 않도록 child -> parent 방향도 fallback으로 확인한다.
        """
        ancestor_node_ids: set[UUID] = set()
        ancestor_edge_ids: set[UUID] = set()

        current = node
        visited_node_ids: set[UUID] = set()

        while current is not None:
            if current.node_id in visited_node_ids:
                break

            visited_node_ids.add(current.node_id)
            ancestor_node_ids.add(current.node_id)

            if current.parent_node_id is None:
                break

            parent = node_by_id.get(current.parent_node_id)
            if parent is None:
                break

            parent_child_edge = active_edge_by_parent_child.get(
                (parent.node_id, current.node_id),
            )
            child_parent_edge = active_edge_by_parent_child.get(
                (current.node_id, parent.node_id),
            )

            if parent_child_edge is not None:
                ancestor_edge_ids.add(parent_child_edge.edge_id)
            elif child_parent_edge is not None:
                ancestor_edge_ids.add(child_parent_edge.edge_id)

            current = parent

        return ancestor_node_ids, ancestor_edge_ids

    def _resolve_root_node_id(
        self,
        *,
        nodes: list[Node],
        excluded_root_node_ids: set[UUID] | None = None,
    ) -> str | None:
        if not nodes:
            return None

        excluded_root_node_ids = excluded_root_node_ids or set()
        node_by_id = {
            node.node_id: node
            for node in nodes
        }

        explicit_root = next(
            (
                node
                for node in nodes
                if node.parent_node_id is None
                and node.node_id not in excluded_root_node_ids
            ),
            None,
        )

        if explicit_root is not None:
            return str(explicit_root.node_id)

        fallback_root = next(
            (
                node
                for node in nodes
                if node.parent_node_id not in node_by_id
            ),
            nodes[0],
        )

        return str(fallback_root.node_id)

    def _resolve_root_node_id_for_node(
        self,
        *,
        node: Node,
        node_by_id: dict[UUID, Node],
    ) -> UUID:
        current = node
        visited_node_ids: set[UUID] = set()

        while current.parent_node_id is not None:
            if current.node_id in visited_node_ids:
                break

            visited_node_ids.add(current.node_id)
            parent = node_by_id.get(current.parent_node_id)

            if parent is None:
                break

            if node.sub_graph_id is not None and parent.sub_graph_id != node.sub_graph_id:
                break

            current = parent

        return current.node_id

    def _build_node_snapshot(
        self,
        *,
        node: Node,
        used_in_generation: bool,
        reference: Reference | None = None,
    ) -> dict:
        return {
            "node_id": str(node.node_id),
            "type": self._node_type_value(node),
            "node_text": node.node_text,
            "position": [
                self._nullable_float(node.position_x),
                self._nullable_float(node.position_y),
                self._nullable_float(node.position_z),
            ],
            "parent_node_id": str(node.parent_node_id) if node.parent_node_id else None,
            "used_in_generation": used_in_generation,
            "data": self._build_node_data_snapshot(
                node=node,
                reference=reference,
            ),
        }

    def _build_edge_snapshot(
        self,
        *,
        edge: Edge,
        node_by_id: dict[UUID, Node],
        active_edge_by_parent_child: dict[tuple[UUID, UUID], Edge],
        used_in_generation: bool,
    ) -> dict:
        from_node = node_by_id.get(edge.from_node_id)
        to_node = node_by_id.get(edge.to_node_id)
        snapshot_to_node_id = edge.to_node_id

        if (
            from_node is not None
            and to_node is not None
            and self._is_part_property_edge(
                from_node=from_node,
                to_node=to_node,
            )
        ):
            snapshot_to_node_id = self._resolve_root_node_id_for_node(
                node=to_node,
                node_by_id=node_by_id,
            )

        return {
            "edge_id": str(edge.edge_id),
            "from_node_id": str(edge.from_node_id),
            "to_node_id": str(snapshot_to_node_id),
            "label": edge.label,
            "used_in_generation": used_in_generation,
        }

    def _build_core_2d_image_snapshot(
        self,
        *,
        core_2d_image: dict | None,
    ) -> dict | None:
        return dict(core_2d_image) if core_2d_image is not None else None

    def _find_latest_core_2d_image_snapshot(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> dict | None:
        latest_snapshot = self.find_latest_graph_snapshot_by_room_id(
            db=db,
            room_id=room_id,
        )

        if latest_snapshot is None:
            return None

        snapshot_data = self.load_snapshot_data(
            graph_snapshot=latest_snapshot,
        )
        core_2d_image = snapshot_data.get("core_2d_image")

        return core_2d_image if isinstance(core_2d_image, dict) else None

    def _build_node_data_snapshot(
        self,
        *,
        node: Node,
        reference: Reference | None = None,
    ) -> dict:
        """
        Node 모델에 JSON/data 컬럼이 있으면 snapshot에 최대한 반영하고,
        REFERENCE node에는 batch 조회한 이미지 metadata를 data로 추가한다.
        """
        data: dict = {}

        for attr_name in ("data", "metadata", "extra_data"):
            value = getattr(node, attr_name, None)

            if isinstance(value, dict):
                data.update(value)
                break

            if isinstance(value, str) and value.strip():
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        data.update(parsed)
                        break
                except json.JSONDecodeError:
                    continue

        if (
            reference is not None
            and self._node_type_value(node) == NodeType.REFERENCE.value
        ):
            data.update(
                {
                    "reference_url": reference.image_url,
                    "mime_type": reference.mime_type,
                    "width": reference.width,
                    "height": reference.height,
                }
            )

        return data

    def _node_type_value(self, node: Node) -> str:
        node_type = node.node_type
        return node_type.value if hasattr(node_type, "value") else str(node_type)

    def _nullable_float(self, value) -> float | None:
        if value is None:
            return None
        return float(value)

    def build_current_graph_snapshot_data(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> dict:
        """
        GET /api/graph 에서 사용한다.
        DB에는 snapshot을 새로 저장하지 않고, 현재 active graph만 response 형태로 build한다.
        """
        all_nodes, all_edges = self.find_graph_by_room_id(
            db=db,
            room_id=room_id,
        )

        latest_version = self.get_latest_graph_version(
            db=db,
            room_id=room_id,
        )

        return self.build_snapshot_data(
            version=latest_version,
            nodes=all_nodes,
            edges=all_edges,
            reference_by_node_id=self.find_references_by_node_ids(
                db=db,
                node_ids=[node.node_id for node in all_nodes],
            ),
            core_2d_image=self._find_latest_core_2d_image_snapshot(
                db=db,
                room_id=room_id,
            ),
        )

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

    def find_sub_graph_by_id(
        self,
        db: Session,
        *,
        room_id: UUID,
        sub_graph_id: UUID,
    ) -> SubGraph | None:
        return (
            db.query(SubGraph)
            .filter(
                SubGraph.room_id == room_id,
                SubGraph.sub_graph_id == sub_graph_id,
            )
            .first()
        )

    def create_reference(
        self,
        db: Session,
        *,
        room_id: UUID,
        node_id: UUID,
        image_url: str,
        mime_type: str,
        width: int,
        height: int,
    ) -> Reference:
        reference = Reference(
            room_id=room_id,
            node_id=node_id,
            query_text=None,
            image_url=image_url,
            mime_type=mime_type,
            width=width,
            height=height,
        )

        db.add(reference)
        db.flush()
        return reference

    def find_references_by_node_ids(
        self,
        db: Session,
        *,
        node_ids: list[UUID],
    ) -> dict[UUID, Reference]:
        references = self.find_reference_records_by_node_ids(
            db=db,
            node_ids=node_ids,
        )
        reference_by_node_id: dict[UUID, Reference] = {}

        for reference in references:
            if reference.node_id is not None:
                reference_by_node_id.setdefault(reference.node_id, reference)

        return reference_by_node_id

    def find_reference_records_by_node_ids(
        self,
        db: Session,
        *,
        node_ids: list[UUID],
    ) -> list[Reference]:
        if not node_ids:
            return []

        return (
            db.query(Reference)
            .filter(Reference.node_id.in_(node_ids))
            .order_by(Reference.created_at.desc(), Reference.reference_id.desc())
            .all()
        )

    def delete_references(self, *, db: Session, references: list[Reference]) -> None:
        for reference in references:
            db.delete(reference)

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

    def update_node_sub_graph(
        self,
        *,
        node: Node,
        sub_graph_id: UUID | None,
    ) -> Node:
        node.sub_graph_id = sub_graph_id
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
            self.soft_delete_node(
                node=node,
                deleted_at=deleted_at,
            )

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
        children = self.find_active_child_nodes(
            db=db,
            room_id=room_id,
            parent_node_id=parent_node_id,
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
        label: str | None = None,
    ) -> Edge:
        edge = Edge(
            room_id=room_id,
            sub_graph_id=sub_graph_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            label=label,
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
            self.soft_delete_edge(
                edge=edge,
                deleted_at=deleted_at,
            )

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
        graph_snapshot_id: UUID | None = None,
        related_fact_id: UUID | None = None,
    ) -> GraphEvent:
        graph_event = GraphEvent(
            room_id=room_id,
            user_id=user_id,
            node_id=node_id,
            edge_id=edge_id,
            graph_snapshot_id=graph_snapshot_id,
            related_fact_id=related_fact_id,
            event_type=event_type,
            payload=json.dumps(payload, ensure_ascii=False, default=str),
        )

        db.add(graph_event)
        db.flush()

        return graph_event

    def find_graph_history_snapshots_by_room_id(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> list[GraphSnapshot]:
        """
        GET /api/history 에서 사용한다.
        NODE_MOVE를 제외하고 graph_event에 연결된 snapshot만 시간순으로 반환한다.
        """
        return (
            db.query(GraphSnapshot)
            .join(
                GraphEvent,
                GraphEvent.graph_snapshot_id == GraphSnapshot.graph_snapshot_id,
            )
            .filter(
                GraphEvent.room_id == room_id,
                GraphEvent.event_type != GraphEventType.NODE_MOVE,
                GraphEvent.graph_snapshot_id.isnot(None),
            )
            .order_by(GraphEvent.created_at.asc(), GraphEvent.graph_event_id.asc())
            .all()
        )

    def find_latest_graph_snapshot_by_room_id(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> GraphSnapshot | None:
        return (
            db.query(GraphSnapshot)
            .filter(GraphSnapshot.room_id == room_id)
            .order_by(GraphSnapshot.version.desc(), GraphSnapshot.created_at.desc())
            .first()
        )

    def find_graph_snapshot_by_id(
        self,
        db: Session,
        *,
        room_id: UUID,
        graph_snapshot_id: UUID,
    ) -> GraphSnapshot | None:
        return (
            db.query(GraphSnapshot)
            .filter(
                GraphSnapshot.room_id == room_id,
                GraphSnapshot.graph_snapshot_id == graph_snapshot_id,
            )
            .first()
        )

    def load_snapshot_data(
        self,
        *,
        graph_snapshot: GraphSnapshot,
    ) -> dict:
        if isinstance(graph_snapshot.snapshot_data, dict):
            return graph_snapshot.snapshot_data
        return json.loads(graph_snapshot.snapshot_data)

    # =========================
    # Graph Interaction - Snapshot
    # =========================

    def create_graph_snapshot_from_current_graph(
        self,
        db: Session,
        *,
        room_id: UUID,
        core_2d_image: dict | None = None,
        generation_context: dict | None = None,
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
            reference_by_node_id=self.find_references_by_node_ids(
                db=db,
                node_ids=[node.node_id for node in all_nodes],
            ),
            core_2d_image=(
                core_2d_image
                if core_2d_image is not None
                else self._find_latest_core_2d_image_snapshot(
                    db=db,
                    room_id=room_id,
                )
            ),
            generation_context=generation_context,
        )

        graph_snapshot = GraphSnapshot(
            room_id=room_id,
            snapshot_data=json.dumps(snapshot_data, ensure_ascii=False, default=str),
            version=next_version,
        )

        db.add(graph_snapshot)
        db.flush()

        return graph_snapshot

    def create_graph_snapshot_from_input_snapshot(
        self,
        db: Session,
        *,
        room_id: UUID,
        input_graph_snapshot_id: UUID,
        core_2d_image: dict,
    ) -> GraphSnapshot:
        input_snapshot = self.find_graph_snapshot_by_id(
            db=db,
            room_id=room_id,
            graph_snapshot_id=input_graph_snapshot_id,
        )
        if input_snapshot is None:
            raise ValueError("Generation Input Snapshot을 찾을 수 없습니다.")

        input_snapshot_data = self.load_snapshot_data(
            graph_snapshot=input_snapshot,
        )
        result_snapshot_data = json.loads(
            json.dumps(input_snapshot_data, ensure_ascii=False, default=str),
        )
        next_version = self.get_next_graph_version(
            db=db,
            room_id=room_id,
        )
        result_snapshot_data["graph_version"] = next_version
        result_snapshot_data["core_2d_image"] = dict(core_2d_image)

        result_snapshot = GraphSnapshot(
            room_id=room_id,
            snapshot_data=json.dumps(
                result_snapshot_data,
                ensure_ascii=False,
                default=str,
            ),
            version=next_version,
        )
        db.add(result_snapshot)
        db.flush()
        return result_snapshot

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
    
    def find_history_snapshots_by_room_id(
        self,
        *,
        db: Session,
        room_id: UUID,
    ) -> list[tuple[GraphEvent, GraphSnapshot]]:
        """
        Snapshot이 연결된 모든 graph event를 시간순으로 반환한다.
        위치만 바뀌고 snapshot을 생성하지 않는 NODE_MOVE만 제외하므로
        GENERATE_2D에 연결된 snapshot도 히스토리에 포함된다.
        """
        stmt = (
            select(GraphEvent, GraphSnapshot)
            .join(
                GraphSnapshot,
                GraphEvent.graph_snapshot_id == GraphSnapshot.graph_snapshot_id,
            )
            .where(
                GraphEvent.room_id == room_id,
                GraphEvent.graph_snapshot_id.is_not(None),
                GraphEvent.event_type != GraphEventType.NODE_MOVE,
            )
            .order_by(
                GraphEvent.created_at.asc(),
                GraphEvent.graph_event_id.asc(),
            )
        )

        return db.execute(stmt).all()
