from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.model.graph import Node, Edge, GraphSnapshot
from app.model.enum import GraphEventType, NodeType
from app.repository.graph_repository import GraphRepository

logger = get_logger(__name__)


class GraphInteractionService:

    def __init__(self, db: Session):
        self.db = db
        self.graph_repository = GraphRepository()

    async def handle_graph_interaction(
        self,
        *,
        event_type: str,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> dict | None:
        logger.info(
            "[graph_interaction] event_type=%s | room_id=%s | user_id=%s",
            event_type,
            room_id,
            user_id,
        )

        try:
            if event_type == "NODE_CREATE":
                return await self._handle_node_save(
                    room_id=room_id,
                    user_id=user_id,
                    payload=payload,
                )

            if event_type == "NODE_MOVE":
                await self._handle_node_move(
                    room_id=room_id,
                    user_id=user_id,
                    payload=payload,
                )
                return None

            if event_type == "NODE_TEXT_UPDATE":
                await self._handle_node_text_update(
                    room_id=room_id,
                    user_id=user_id,
                    payload=payload,
                )
                return None

            if event_type == "NODE_DELETE":
                await self._handle_node_delete(
                    room_id=room_id,
                    user_id=user_id,
                    payload=payload,
                )
                return None

            if event_type == "EDGE_CREATE":
                return await self._handle_edge_create(
                    room_id=room_id,
                    user_id=user_id,
                    payload=payload,
                )

            if event_type == "EDGE_DELETE":
                await self._handle_edge_delete(
                    room_id=room_id,
                    user_id=user_id,
                    payload=payload,
                )
                return None

            raise ValueError(
                f"[GRAPH400] Unsupported graph interaction event_type: {event_type}"
            )

        except Exception:
            self.db.rollback()

            logger.exception(
                "[graph_interaction_failed] event_type=%s | room_id=%s | user_id=%s | payload=%s",
                event_type,
                room_id,
                user_id,
                payload,
            )

            raise

    async def _handle_node_save(
        self,
        *,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> dict:
        logger.info(
            "[node_create_start] room_id=%s | user_id=%s | payload=%s",
            room_id,
            user_id,
            payload,
        )

        job_id = self._parse_uuid_payload(
            payload=payload,
            key="job_id",
        )

        parent_node_id = self._parse_optional_uuid_payload(
            payload=payload,
            key="parent_node_id",
        )

        sub_graph_id = self._parse_optional_uuid_payload(
            payload=payload,
            key="sub_graph_id",
        )

        node_text = self._get_required_str(
            payload=payload,
            key="node_text",
        ).strip()

        if not node_text:
            raise ValueError("[GRAPH400] node_text must not be blank")

        x, y, z = self._parse_position_payload(payload=payload)
        requested_node_type = self._parse_optional_node_type(payload=payload)

        edge: Edge | None = None

        
        parent_node = self._get_active_node_or_raise(
            room_id=room_id,
            node_id=parent_node_id,
        )

        resolved_sub_graph_id = parent_node.sub_graph_id

        if sub_graph_id is not None and sub_graph_id != resolved_sub_graph_id:
            raise ValueError(
                "[GRAPH400] sub_graph_id does not match parent_node's sub_graph_id"
        )

        sub_graph_id = resolved_sub_graph_id
        node_type = requested_node_type or NodeType.PROPERTY

        logger.info(
            "[node_create_payload_parsed] room_id=%s | user_id=%s | job_id=%s | parent_node_id=%s | sub_graph_id=%s | node_text=%s | node_type=%s | position=%s",
            room_id,
            user_id,
            job_id,
            parent_node_id,
            sub_graph_id,
            node_text,
            self._node_type_value_from_enum(node_type),
            [x, y, z],
        )

        node = self.graph_repository.create_node(
            db=self.db,
            room_id=room_id,
            sub_graph_id=sub_graph_id,
            parent_node_id=parent_node_id,
            node_text=node_text,
            node_type=node_type,
            position_x=x,
            position_y=y,
            position_z=z,
        )

        if parent_node_id is not None:
            edge = self.graph_repository.create_edge(
                db=self.db,
                room_id=room_id,
                sub_graph_id=sub_graph_id,
                from_node_id=parent_node_id,
                to_node_id=node.node_id,
            )

            logger.info(
                "[node_create_edge_created] room_id=%s | edge_id=%s | from_node_id=%s | to_node_id=%s",
                room_id,
                edge.edge_id,
                parent_node_id,
                node.node_id,
            )

        graph_snapshot = self.graph_repository.create_graph_snapshot_from_current_graph(
            db=self.db,
            room_id=room_id,
        )

        self.graph_repository.create_graph_event(
            db=self.db,
            room_id=room_id,
            user_id=user_id,
            event_type=GraphEventType.NODE_CREATE,
            node_id=node.node_id,
            edge_id=edge.edge_id if edge else None,
            graph_snapshot_id=graph_snapshot.graph_snapshot_id,
            payload={
                "interaction_type": "NODE_CREATE",
                "job_id": str(job_id),
                "parent_node_id": str(parent_node_id) if parent_node_id else None,
                "sub_graph_id": str(sub_graph_id) if sub_graph_id else None,
                "node_text": node_text,
                "node_type": self._node_type_value(node),
                "position": [x, y, z],
                "created_node_id": str(node.node_id),
                "created_edge_id": str(edge.edge_id) if edge else None,
                "graph_snapshot_id": str(graph_snapshot.graph_snapshot_id),
            },
        )

        self.db.commit()

        logger.info(
            "[node_create_saved] room_id=%s | user_id=%s | job_id=%s | node_id=%s | parent_node_id=%s | sub_graph_id=%s | edge_id=%s | graph_snapshot_id=%s",
            room_id,
            user_id,
            job_id,
            node.node_id,
            parent_node_id,
            sub_graph_id,
            edge.edge_id if edge else None,
            graph_snapshot.graph_snapshot_id,
        )

        return {
            "isSuccess": True,
            "code": "NODE200",
            "message": "노드 생성 성공",
            "result": {
                "job_id": str(job_id),
                "node_id": str(node.node_id),
                "graph_snapshot_id": str(graph_snapshot.graph_snapshot_id),
            },
        }

    # =========================
    # NODE_MOVE
    # =========================

    async def _handle_node_move(
        self,
        *,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> None:
        node_id = self._parse_uuid_payload(
            payload=payload,
            key="node_id",
        )

        x, y, z = self._parse_position_payload(payload=payload)

        node = self._get_active_node_or_raise(
            room_id=room_id,
            node_id=node_id,
        )

        before_position = self._node_position(node=node)

        self.graph_repository.update_node_position(
            node=node,
            x=x,
            y=y,
            z=z,
        )

        self.graph_repository.create_graph_event(
            db=self.db,
            room_id=room_id,
            user_id=user_id,
            node_id=node.node_id,
            event_type=GraphEventType.NODE_MOVE,
            graph_snapshot_id=None,
            payload={
                "interaction_type": "NODE_MOVE",
                "node_id": str(node.node_id),
                "before_position": before_position,
                "after_position": [x, y, z],
                "graph_snapshot_id": None,
            },
        )

        self.db.commit()

        logger.info(
            "[node_move_saved] room_id=%s | user_id=%s | node_id=%s | position=%s",
            room_id,
            user_id,
            node_id,
            [x, y, z],
        )

    # =========================
    # NODE_TEXT_UPDATE
    # =========================

    async def _handle_node_text_update(
        self,
        *,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> None:
        node_id = self._parse_uuid_payload(
            payload=payload,
            key="node_id",
        )

        text = self._get_required_str(
            payload=payload,
            key="text",
        ).strip()

        if not text:
            raise ValueError("[GRAPH400] node text must not be blank")

        node = self._get_active_node_or_raise(
            room_id=room_id,
            node_id=node_id,
        )

        before_text = node.node_text

        self.graph_repository.update_node_text(
            node=node,
            text=text,
        )

        graph_snapshot = self.graph_repository.create_graph_snapshot_from_current_graph(
            db=self.db,
            room_id=room_id,
        )

        self.graph_repository.create_graph_event(
            db=self.db,
            room_id=room_id,
            user_id=user_id,
            node_id=node.node_id,
            event_type=GraphEventType.NODE_TEXT_UPDATE,
            graph_snapshot_id=graph_snapshot.graph_snapshot_id,
            payload={
                "interaction_type": "NODE_TEXT_UPDATE",
                "node_id": str(node.node_id),
                "before_text": before_text,
                "after_text": text,
                "graph_snapshot_id": str(graph_snapshot.graph_snapshot_id),
            },
        )

        self.db.commit()

        logger.info(
            "[node_text_update_saved] room_id=%s | user_id=%s | node_id=%s | graph_snapshot_id=%s",
            room_id,
            user_id,
            node_id,
            graph_snapshot.graph_snapshot_id,
        )

    # =========================
    # NODE_DELETE
    # =========================

    async def _handle_node_delete(
        self,
        *,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> None:
        node_id = self._parse_uuid_payload(
            payload=payload,
            key="node_id",
        )

        node = self._get_active_node_or_raise(
            room_id=room_id,
            node_id=node_id,
        )

        deleted_at = datetime.now(timezone.utc)

        child_nodes = self.graph_repository.find_active_child_nodes_recursively(
            db=self.db,
            room_id=room_id,
            parent_node_id=node.node_id,
        )

        nodes_to_delete = [
            node,
            *child_nodes,
        ]

        node_ids_to_delete = [
            target_node.node_id
            for target_node in nodes_to_delete
        ]

        connected_edges = self.graph_repository.find_active_edges_connected_to_nodes(
            db=self.db,
            room_id=room_id,
            node_ids=node_ids_to_delete,
        )

        self.graph_repository.soft_delete_nodes(
            nodes=nodes_to_delete,
            deleted_at=deleted_at,
        )

        self.graph_repository.soft_delete_edges(
            edges=connected_edges,
            deleted_at=deleted_at,
        )

        graph_snapshot = self.graph_repository.create_graph_snapshot_from_current_graph(
            db=self.db,
            room_id=room_id,
        )

        self.graph_repository.create_graph_event(
            db=self.db,
            room_id=room_id,
            user_id=user_id,
            node_id=node.node_id,
            event_type=GraphEventType.NODE_DELETE,
            graph_snapshot_id=graph_snapshot.graph_snapshot_id,
            payload={
                "interaction_type": "NODE_DELETE",
                "node_id": str(node.node_id),
                "deleted_child_node_ids": [
                    str(child_node.node_id)
                    for child_node in child_nodes
                ],
                "deleted_node_ids": [
                    str(target_node.node_id)
                    for target_node in nodes_to_delete
                ],
                "deleted_edge_ids": [
                    str(edge.edge_id)
                    for edge in connected_edges
                ],
                "graph_snapshot_id": str(graph_snapshot.graph_snapshot_id),
            },
        )

        self.db.commit()

        logger.info(
            "[node_delete_saved] room_id=%s | user_id=%s | node_id=%s | deleted_child_nodes=%s | deleted_edges=%s | graph_snapshot_id=%s",
            room_id,
            user_id,
            node_id,
            len(child_nodes),
            len(connected_edges),
            graph_snapshot.graph_snapshot_id,
        )

    # =========================
    # EDGE_CREATE
    # =========================

    async def _handle_edge_create(
        self,
        *,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> dict:
        job_id = self._parse_uuid_payload(
            payload=payload,
            key="job_id",
        )

        from_node_id = self._parse_uuid_payload(
            payload=payload,
            key="from_node_id",
        )

        to_node_id = self._parse_uuid_payload(
            payload=payload,
            key="to_node_id",
        )

        if from_node_id == to_node_id:
            raise ValueError(
                "[GRAPH400] from_node_id and to_node_id must be different"
            )

        from_node = self._get_active_node_or_raise(
            room_id=room_id,
            node_id=from_node_id,
        )

        to_node = self._get_active_node_or_raise(
            room_id=room_id,
            node_id=to_node_id,
        )

        self._validate_edge_create_policy(
            from_node=from_node,
            to_node=to_node,
        )

        existing_edge = self.graph_repository.find_active_edge_between_nodes(
            db=self.db,
            room_id=room_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
        )

        if existing_edge is not None:
            raise ValueError(
                f"[GRAPH409] Edge already exists: edge_id={existing_edge.edge_id}"
            )

        label = self._get_optional_str(
            payload=payload,
            key="label",
        )

        edge = self.graph_repository.create_edge(
            db=self.db,
            room_id=room_id,
            # PART -> PROPERTY cross edge는 서로 다른 sub_graph를 연결할 수 있다.
            # DB에는 Unity가 보낸 from/to를 그대로 저장하고, snapshot에서만 to_node_id를 root로 변환한다.
            sub_graph_id=from_node.sub_graph_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            label=label,
        )

        graph_snapshot = self.graph_repository.create_graph_snapshot_from_current_graph(
            db=self.db,
            room_id=room_id,
        )

        self.graph_repository.create_graph_event(
            db=self.db,
            room_id=room_id,
            user_id=user_id,
            edge_id=edge.edge_id,
            event_type=GraphEventType.EDGE_CREATE,
            graph_snapshot_id=graph_snapshot.graph_snapshot_id,
            payload={
                "interaction_type": "EDGE_CREATE",
                "job_id": str(job_id),
                "edge_id": str(edge.edge_id),
                "from_node_id": str(from_node_id),
                "to_node_id": str(to_node_id),
                "label": edge.label,
                "from_node_type": self._node_type_value(from_node),
                "to_node_type": self._node_type_value(to_node),
                "graph_snapshot_id": str(graph_snapshot.graph_snapshot_id),
            },
        )

        self.db.commit()

        logger.info(
            "[edge_create_saved] room_id=%s | user_id=%s | edge_id=%s | from_node_id=%s | to_node_id=%s | graph_snapshot_id=%s",
            room_id,
            user_id,
            edge.edge_id,
            from_node_id,
            to_node_id,
            graph_snapshot.graph_snapshot_id,
        )

        return {
            "isSuccess": True,
            "code": "EDGE200",
            "message": "엣지 생성 성공",
            "result": {
                "job_id": str(job_id),
                "edge_id": str(edge.edge_id),
                "graph_snapshot_id": str(graph_snapshot.graph_snapshot_id),
            },
        }

    # =========================
    # EDGE_DELETE
    # =========================

    async def _handle_edge_delete(
        self,
        *,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> None:
        edge_id = self._parse_uuid_payload(
            payload=payload,
            key="edge_id",
        )

        edge = self._get_active_edge_or_raise(
            room_id=room_id,
            edge_id=edge_id,
        )

        from_node = self._get_active_node_or_raise(
            room_id=room_id,
            node_id=edge.from_node_id,
        )
        to_node = self._get_active_node_or_raise(
            room_id=room_id,
            node_id=edge.to_node_id,
        )

        before_payload = {
            "edge_id": str(edge.edge_id),
            "from_node_id": str(edge.from_node_id),
            "to_node_id": str(edge.to_node_id),
            "label": edge.label,
            "from_node_type": self._node_type_value(from_node),
            "to_node_type": self._node_type_value(to_node),
        }

        deleted_at = datetime.now(timezone.utc)

        self.graph_repository.soft_delete_edge(
            edge=edge,
            deleted_at=deleted_at,
        )

        graph_snapshot = self.graph_repository.create_graph_snapshot_from_current_graph(
            db=self.db,
            room_id=room_id,
        )

        self.graph_repository.create_graph_event(
            db=self.db,
            room_id=room_id,
            user_id=user_id,
            edge_id=edge.edge_id,
            event_type=GraphEventType.EDGE_DELETE,
            graph_snapshot_id=graph_snapshot.graph_snapshot_id,
            payload={
                "interaction_type": "EDGE_DELETE",
                **before_payload,
                "graph_snapshot_id": str(graph_snapshot.graph_snapshot_id),
            },
        )

        self.db.commit()

        logger.info(
            "[edge_delete_saved] room_id=%s | user_id=%s | edge_id=%s | graph_snapshot_id=%s",
            room_id,
            user_id,
            edge_id,
            graph_snapshot.graph_snapshot_id,
        )

    # =========================
    # Entity helpers
    # =========================

    def _get_active_node_or_raise(
        self,
        *,
        room_id: UUID,
        node_id: UUID,
    ) -> Node:
        node = self.graph_repository.find_active_node_by_id(
            db=self.db,
            room_id=room_id,
            node_id=node_id,
        )

        if node is None:
            raise ValueError(
                f"[NODE404] Node not found or already deleted: node_id={node_id}"
            )

        return node

    def _get_active_edge_or_raise(
        self,
        *,
        room_id: UUID,
        edge_id: UUID,
    ) -> Edge:
        edge = self.graph_repository.find_active_edge_by_id(
            db=self.db,
            room_id=room_id,
            edge_id=edge_id,
        )

        if edge is None:
            raise ValueError(
                f"[EDGE404] Edge not found or already deleted: edge_id={edge_id}"
            )

        return edge

    def _validate_edge_create_policy(
        self,
        *,
        from_node: Node,
        to_node: Node,
    ) -> None:
        from_type = self._node_type_value(from_node)
        to_type = self._node_type_value(to_node)

        is_part_property_edge = (
            from_type == NodeType.PART.value
            and to_type == NodeType.PROPERTY.value
        )
        is_part_reference_edge = (
            from_type == NodeType.PART.value
            and to_type == NodeType.REFERENCE.value
        )

        if is_part_property_edge or is_part_reference_edge:
            return

        if from_node.sub_graph_id != to_node.sub_graph_id:
            raise ValueError(
                "[GRAPH409] Cannot create non PART-PROPERTY edge between nodes in different sub_graphs"
            )

    # =========================
    # Payload helpers
    # =========================

    def _parse_optional_uuid_payload(
        self,
        *,
        payload: dict,
        key: str,
    ) -> UUID | None:
        value = payload.get(key)

        if value is None or value == "":
            return None

        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            raise ValueError(
                f"[GRAPH400] Invalid UUID field: {key}={payload.get(key)}"
            )

    def _parse_uuid_payload(
        self,
        *,
        payload: dict,
        key: str,
    ) -> UUID:
        if key not in payload:
            raise ValueError(f"[GRAPH400] Missing required field: {key}")

        try:
            return UUID(str(payload[key]))
        except (TypeError, ValueError):
            raise ValueError(
                f"[GRAPH400] Invalid UUID field: {key}={payload.get(key)}"
            )

    def _parse_optional_node_type(
        self,
        *,
        payload: dict,
    ):
        value = payload.get("node_type")

        if value is None or value == "":
            return None

        try:
            return NodeType(str(value))
        except ValueError:
            try:
                return NodeType[str(value)]
            except KeyError:
                raise ValueError(f"[GRAPH400] Invalid node_type: {value}")

    def _parse_position_payload(
        self,
        *,
        payload: dict,
    ) -> tuple[float, float, float]:
        position = payload.get("position")

        if not isinstance(position, list) or len(position) != 3:
            raise ValueError("[GRAPH400] Field must be array of length 3: position")

        try:
            return float(position[0]), float(position[1]), float(position[2])
        except (TypeError, ValueError):
            raise ValueError(
                f"[GRAPH400] Position values must be numbers: position={position}"
            )

    def _get_required_dict(
        self,
        *,
        payload: dict,
        key: str,
    ) -> dict:
        if key not in payload:
            raise ValueError(f"[GRAPH400] Missing required field: {key}")

        value = payload[key]

        if not isinstance(value, dict):
            raise ValueError(f"[GRAPH400] Field must be object: {key}")

        return value

    def _get_required_str(
        self,
        *,
        payload: dict,
        key: str,
    ) -> str:
        if key not in payload:
            raise ValueError(f"[GRAPH400] Missing required field: {key}")

        value = payload[key]

        if value is None:
            raise ValueError(f"[GRAPH400] Field must not be null: {key}")

        return str(value)

    def _get_optional_str(
        self,
        *,
        payload: dict,
        key: str,
    ) -> str | None:
        value = payload.get(key)

        if value is None:
            return None

        text = str(value).strip()
        return text if text else None

    def _get_required_float(
        self,
        data: dict,
        key: str,
    ) -> float:
        if key not in data:
            raise ValueError(f"[GRAPH400] Missing required position field: {key}")

        try:
            return float(data[key])
        except (TypeError, ValueError):
            raise ValueError(
                f"[GRAPH400] Position field must be number: {key}={data.get(key)}"
            )

    def _node_position(
        self,
        *,
        node: Node,
    ) -> list[float | None]:
        return [
            float(node.position_x) if node.position_x is not None else None,
            float(node.position_y) if node.position_y is not None else None,
            float(node.position_z) if node.position_z is not None else None,
        ]

    def _node_type_value(self, node: Node) -> str:
        node_type = node.node_type
        return node_type.value if hasattr(node_type, "value") else str(node_type)

    def _node_type_value_from_enum(self, node_type) -> str:
        return node_type.value if hasattr(node_type, "value") else str(node_type)
