from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.model.graph import Node, Edge
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
    ) -> dict:
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
                    payload=payload
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

        parent_node_id = self._parse_optional_uuid_payload(
            payload=payload,
            key="parent_node_id",
        )

        node_text = self._get_required_str(
            payload=payload,
            key="node_text",
        ).strip()

        if not node_text:
            raise ValueError("[GRAPH400] node_text must not be blank")

        position = payload.get("position")

        if not isinstance(position, list) or len(position) != 3:
            raise ValueError("[GRAPH400] Field must be array of length 3: position")

        try:
            x = float(position[0])
            y = float(position[1])
            z = float(position[2])
        except (TypeError, ValueError):
            raise ValueError(
                f"[GRAPH400] Position values must be numbers: position={position}"
            )

        logger.info(
            "[node_create_payload_parsed] room_id=%s | user_id=%s | parent_node_id=%s | node_text=%s | position=%s",
            room_id,
            user_id,
            parent_node_id,
            node_text,
            [x, y, z],
        )

        edge = None

        if parent_node_id is not None:
            parent_node = self._get_active_node_or_raise(
                room_id=room_id,
                node_id=parent_node_id,
            )

            sub_graph_id = parent_node.sub_graph_id
            node_type = NodeType.PROPERTY

            logger.info(
                "[node_create_parent_found] room_id=%s | parent_node_id=%s | sub_graph_id=%s",
                room_id,
                parent_node_id,
                sub_graph_id,
            )

        else:
            sub_graph = self.graph_repository.create_sub_graph(
                db=self.db,
                room_id=room_id,
            )

            sub_graph_id = sub_graph.sub_graph_id
            node_type = NodeType.PART

            logger.info(
                "[node_create_sub_graph_created] room_id=%s | sub_graph_id=%s",
                room_id,
                sub_graph_id,
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

        logger.info(
            "[node_created] room_id=%s | user_id=%s | node_id=%s | parent_node_id=%s | sub_graph_id=%s | node_type=%s",
            room_id,
            user_id,
            node.node_id,
            parent_node_id,
            sub_graph_id,
            node_type,
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

        else:
            logger.info(
                "[node_create_edge_skipped] room_id=%s | node_id=%s | reason=root_node",
                room_id,
                node.node_id,
            )

        self.graph_repository.create_graph_event(
            db=self.db,
            room_id=room_id,
            user_id=user_id,
            event_type=GraphEventType.NODE_CREATE,
            node_id=node.node_id,
            edge_id=edge.edge_id if edge else None,
            payload={
                "interaction_type": "NODE_CREATE",
                "parent_node_id": str(parent_node_id) if parent_node_id else None,
                "sub_graph_id": str(sub_graph_id),
                "node_text": node_text,
                "position": [x, y, z],
                "created_node_id": str(node.node_id),
                "created_edge_id": str(edge.edge_id) if edge else None,
            },
        )

        logger.info(
            "[node_create_event_saved] room_id=%s | user_id=%s | node_id=%s | edge_id=%s",
            room_id,
            user_id,
            node.node_id,
            edge.edge_id if edge else None,
        )

        self.graph_repository.create_graph_snapshot_from_current_graph(
            db=self.db,
            room_id=room_id,
        )

        logger.info(
            "[node_create_snapshot_saved] room_id=%s | node_id=%s",
            room_id,
            node.node_id,
        )

        self.db.commit()

        logger.info(
            "[node_create_saved] room_id=%s | user_id=%s | node_id=%s | parent_node_id=%s | sub_graph_id=%s | edge_id=%s | position=%s",
            room_id,
            user_id,
            node.node_id,
            parent_node_id,
            sub_graph_id,
            edge.edge_id if edge else None,
            [x, y, z],
        )
        
        return {
            "node_id" : node.node_id,
            "node_type" : node.node_type
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

        position = self._get_required_dict(
            payload=payload,
            key="position",
        )

        x = self._get_required_float(position, "x")
        y = self._get_required_float(position, "y")
        z = self._get_required_float(position, "z")

        node = self._get_active_node_or_raise(
            room_id=room_id,
            node_id=node_id,
        )

        before_position = {
            "x": node.position_x,
            "y": node.position_y,
            "z": node.position_z,
        }

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
            payload={
                "interaction_type": "NODE_MOVE",
                "node_id": str(node.node_id),
                "before_position": before_position,
                "after_position": {
                    "x": x,
                    "y": y,
                    "z": z,
                },
            },
        )

        # NODE_MOVE는 드래그 중 자주 발생할 수 있으므로 snapshot 생성하지 않음.
        self.db.commit()

        logger.info(
            "[node_move_saved] room_id=%s | user_id=%s | node_id=%s | position=%s",
            room_id,
            user_id,
            node_id,
            {"x": x, "y": y, "z": z},
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

        self.graph_repository.create_graph_event(
            db=self.db,
            room_id=room_id,
            user_id=user_id,
            node_id=node.node_id,
            event_type=GraphEventType.NODE_TEXT_UPDATE,
            payload={
                "interaction_type": "NODE_TEXT_UPDATE",
                "node_id": str(node.node_id),
                "before_text": before_text,
                "after_text": text,
            },
        )

        self.graph_repository.create_graph_snapshot_from_current_graph(
            db=self.db,
            room_id=room_id,
        )

        self.db.commit()

        logger.info(
            "[node_text_update_saved] room_id=%s | user_id=%s | node_id=%s",
            room_id,
            user_id,
            node_id,
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

        self.graph_repository.create_graph_event(
            db=self.db,
            room_id=room_id,
            user_id=user_id,
            node_id=node.node_id,
            event_type=GraphEventType.NODE_DELETE,
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
            },
        )

        self.graph_repository.create_graph_snapshot_from_current_graph(
            db=self.db,
            room_id=room_id,
        )

        self.db.commit()

        logger.info(
            "[node_delete_saved] room_id=%s | user_id=%s | node_id=%s | deleted_child_nodes=%s | deleted_edges=%s",
            room_id,
            user_id,
            node_id,
            len(child_nodes),
            len(connected_edges),
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
    ) -> None:
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

        if from_node.sub_graph_id != to_node.sub_graph_id:
            raise ValueError(
                "[GRAPH409] Cannot create edge between nodes in different sub_graphs"
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

        edge = self.graph_repository.create_edge(
            db=self.db,
            room_id=room_id,
            sub_graph_id=from_node.sub_graph_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
        )

        self.graph_repository.create_graph_event(
            db=self.db,
            room_id=room_id,
            user_id=user_id,
            edge_id=edge.edge_id,
            event_type=GraphEventType.EDGE_CREATE,
            payload={
                "interaction_type": "EDGE_CREATE",
                "edge_id": str(edge.edge_id),
                "from_node_id": str(from_node_id),
                "to_node_id": str(to_node_id),
            },
        )

        self.graph_repository.create_graph_snapshot_from_current_graph(
            db=self.db,
            room_id=room_id,
        )

        self.db.commit()

        logger.info(
            "[edge_create_saved] room_id=%s | user_id=%s | edge_id=%s | from_node_id=%s | to_node_id=%s",
            room_id,
            user_id,
            edge.edge_id,
            from_node_id,
            to_node_id,
        )
        
        return {
            "edge_id" : edge.edge_id
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

        deleted_at = datetime.now(timezone.utc)

        self.graph_repository.soft_delete_edge(
            edge=edge,
            deleted_at=deleted_at,
        )

        self.graph_repository.create_graph_event(
            db=self.db,
            room_id=room_id,
            user_id=user_id,
            edge_id=edge.edge_id,
            event_type=GraphEventType.EDGE_DELETE,
            payload={
                "interaction_type": "EDGE_DELETE",
                "edge_id": str(edge.edge_id),
                "from_node_id": str(edge.from_node_id),
                "to_node_id": str(edge.to_node_id),
                "label": edge.label,
            },
        )

        self.graph_repository.create_graph_snapshot_from_current_graph(
            db=self.db,
            room_id=room_id,
        )

        self.db.commit()

        logger.info(
            "[edge_delete_saved] room_id=%s | user_id=%s | edge_id=%s",
            room_id,
            user_id,
            edge_id,
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