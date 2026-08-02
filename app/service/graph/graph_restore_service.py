import json
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.exceptions import NotFoundException
from app.model.enum import NodeType
from app.model.graph import Edge, Node
from app.model.reference import Reference
from app.repository.graph_repository import GraphRepository
from app.repository.graph_restore_repository import GraphRestoreRepository
from app.repository.room_repository import RoomRepository
from app.schema.graph.restore_response import (
    GraphRestoreCore2DImageResponse,
    GraphRestoreEdgeResponse,
    GraphRestoreNodeResponse,
    GraphRestoreResponse,
    GraphRestoreSubGraphResponse,
)

logger = get_logger(__name__)


class GraphRestoreService:
    """Build the room restoration projection without invoking snapshot builders."""

    def __init__(
        self,
        *,
        restore_repository: GraphRestoreRepository | None = None,
        graph_repository: GraphRepository | None = None,
        room_repository: RoomRepository | None = None,
    ) -> None:
        self.restore_repository = restore_repository or GraphRestoreRepository()
        self.graph_repository = graph_repository or GraphRepository()
        self.room_repository = room_repository or RoomRepository()

    def get_room_graph(
        self,
        *,
        db: Session,
        room_id: UUID,
    ) -> GraphRestoreResponse:
        room = self.room_repository.find_room_by_id(
            db=db,
            room_id=room_id,
        )
        if room is None:
            raise NotFoundException(code=ResponseCode.ROOM404)

        sub_graphs = self.restore_repository.find_non_deleted_sub_graphs_by_room_id(
            db=db,
            room_id=room_id,
        )
        sub_graph_ids = [sub_graph.sub_graph_id for sub_graph in sub_graphs]
        nodes = self.restore_repository.find_non_deleted_nodes_by_sub_graph_ids(
            db=db,
            room_id=room_id,
            sub_graph_ids=sub_graph_ids,
        )
        edges = self.restore_repository.find_non_deleted_edges_by_sub_graph_ids(
            db=db,
            room_id=room_id,
            sub_graph_ids=sub_graph_ids,
        )

        latest_snapshot = self.graph_repository.find_latest_graph_snapshot_by_room_id(
            db=db,
            room_id=room_id,
        )
        latest_snapshot_data = self._load_snapshot_data(latest_snapshot)
        graph_version = self.graph_repository.get_latest_graph_version(
            db=db,
            room_id=room_id,
        )

        node_snapshot_by_id, edge_snapshot_by_id, root_node_id_by_sub_graph_id = (
            self._index_snapshot_data(latest_snapshot_data)
        )
        reference_by_node_id = self.graph_repository.find_references_by_node_ids(
            db=db,
            node_ids=[node.node_id for node in nodes],
        )

        nodes_by_sub_graph_id: dict[UUID, list[Node]] = {
            sub_graph_id: [] for sub_graph_id in sub_graph_ids
        }
        for node in nodes:
            if node.sub_graph_id in nodes_by_sub_graph_id:
                nodes_by_sub_graph_id[node.sub_graph_id].append(node)

        node_sub_graph_id_by_node_id = {
            node.node_id: node.sub_graph_id
            for node in nodes
            if node.sub_graph_id is not None
        }
        edges_by_sub_graph_id: dict[UUID, list[Edge]] = {
            sub_graph_id: [] for sub_graph_id in sub_graph_ids
        }
        for edge in edges:
            resolved_sub_graph_id = edge.sub_graph_id
            if resolved_sub_graph_id is None:
                resolved_sub_graph_id = node_sub_graph_id_by_node_id.get(
                    edge.from_node_id,
                ) or node_sub_graph_id_by_node_id.get(edge.to_node_id)

            if resolved_sub_graph_id in edges_by_sub_graph_id:
                edges_by_sub_graph_id[resolved_sub_graph_id].append(edge)

        response_sub_graphs = [
            self._build_sub_graph_response(
                sub_graph_id=sub_graph_id,
                nodes=nodes_by_sub_graph_id[sub_graph_id],
                edges=edges_by_sub_graph_id[sub_graph_id],
                stored_root_node_id=root_node_id_by_sub_graph_id.get(sub_graph_id),
                node_snapshot_by_id=node_snapshot_by_id,
                edge_snapshot_by_id=edge_snapshot_by_id,
                reference_by_node_id=reference_by_node_id,
            )
            for sub_graph_id in sub_graph_ids
        ]

        return GraphRestoreResponse(
            room_id=room_id,
            graph_version=graph_version,
            core_2d_image=self._parse_core_2d_image(latest_snapshot_data),
            sub_graphs=response_sub_graphs,
        )

    def _build_sub_graph_response(
        self,
        *,
        sub_graph_id: UUID,
        nodes: list[Node],
        edges: list[Edge],
        stored_root_node_id: UUID | None,
        node_snapshot_by_id: dict[UUID, dict[str, Any]],
        edge_snapshot_by_id: dict[UUID, dict[str, Any]],
        reference_by_node_id: dict[UUID, Reference],
    ) -> GraphRestoreSubGraphResponse:
        sorted_nodes = sorted(nodes, key=lambda node: str(node.node_id))
        active_node_ids = {node.node_id for node in sorted_nodes}
        root_node_id = (
            stored_root_node_id
            if stored_root_node_id in active_node_ids
            else next(
                (
                    node.node_id
                    for node in sorted_nodes
                    if node.parent_node_id is None
                ),
                None,
            )
        )

        return GraphRestoreSubGraphResponse(
            sub_graph_id=sub_graph_id,
            root_node_id=root_node_id,
            nodes=[
                self._build_node_response(
                    node=node,
                    snapshot_node=node_snapshot_by_id.get(node.node_id),
                    reference=reference_by_node_id.get(node.node_id),
                )
                for node in sorted_nodes
            ],
            edges=[
                self._build_edge_response(
                    edge=edge,
                    snapshot_edge=edge_snapshot_by_id.get(edge.edge_id),
                )
                for edge in sorted(edges, key=lambda edge: str(edge.edge_id))
            ],
        )

    def _build_node_response(
        self,
        *,
        node: Node,
        snapshot_node: dict[str, Any] | None,
        reference: Reference | None,
    ) -> GraphRestoreNodeResponse:
        data: dict[str, Any] = {}
        if reference is not None and self._node_type_value(node) == NodeType.REFERENCE.value:
            data = {
                "asset_id": reference.reference_id,
                "mime_type": reference.mime_type,
                "width": reference.width,
                "height": reference.height,
                "reference_image_url": reference.image_url,
            }

        return GraphRestoreNodeResponse(
            node_id=node.node_id,
            type=node.node_type,
            node_text=node.node_text,
            position=[
                self._position_value(node.position_x),
                self._position_value(node.position_y),
                self._position_value(node.position_z),
            ],
            parent_node_id=node.parent_node_id,
            used_in_generation=(snapshot_node or {}).get("used_in_generation") is True,
            data=data,
        )

    def _build_edge_response(
        self,
        *,
        edge: Edge,
        snapshot_edge: dict[str, Any] | None,
    ) -> GraphRestoreEdgeResponse:
        return GraphRestoreEdgeResponse(
            edge_id=edge.edge_id,
            from_node_id=edge.from_node_id,
            to_node_id=edge.to_node_id,
            label=edge.label,
            used_in_generation=(snapshot_edge or {}).get("used_in_generation") is True,
        )

    def _load_snapshot_data(self, graph_snapshot) -> dict[str, Any]:
        if graph_snapshot is None:
            return {}

        try:
            snapshot_data = self.graph_repository.load_snapshot_data(
                graph_snapshot=graph_snapshot,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning(
                "[graph_restore_snapshot_invalid] graph_snapshot_id=%s",
                getattr(graph_snapshot, "graph_snapshot_id", None),
            )
            return {}

        return snapshot_data if isinstance(snapshot_data, dict) else {}

    def _index_snapshot_data(
        self,
        snapshot_data: dict[str, Any],
    ) -> tuple[
        dict[UUID, dict[str, Any]],
        dict[UUID, dict[str, Any]],
        dict[UUID, UUID | None],
    ]:
        node_by_id: dict[UUID, dict[str, Any]] = {}
        edge_by_id: dict[UUID, dict[str, Any]] = {}
        root_by_sub_graph_id: dict[UUID, UUID | None] = {}

        for sub_graph in snapshot_data.get("sub_graphs", []):
            if not isinstance(sub_graph, dict):
                continue

            sub_graph_id = self._parse_uuid(sub_graph.get("sub_graph_id"))
            if sub_graph_id is None:
                continue

            root_by_sub_graph_id[sub_graph_id] = self._parse_uuid(
                sub_graph.get("root_node_id"),
            )
            for node in sub_graph.get("nodes", []):
                if not isinstance(node, dict):
                    continue
                node_id = self._parse_uuid(node.get("node_id"))
                if node_id is not None:
                    node_by_id[node_id] = node

            for edge in sub_graph.get("edges", []):
                if not isinstance(edge, dict):
                    continue
                edge_id = self._parse_uuid(edge.get("edge_id"))
                if edge_id is not None:
                    edge_by_id[edge_id] = edge

        return node_by_id, edge_by_id, root_by_sub_graph_id

    def _parse_core_2d_image(
        self,
        snapshot_data: dict[str, Any],
    ) -> GraphRestoreCore2DImageResponse | None:
        core_2d_image = snapshot_data.get("core_2d_image")
        if not isinstance(core_2d_image, dict):
            return None

        try:
            return GraphRestoreCore2DImageResponse.model_validate(core_2d_image)
        except ValidationError:
            logger.warning("[graph_restore_core_2d_image_invalid]")
            return None

    def _node_type_value(self, node: Node) -> str:
        node_type = node.node_type
        return node_type.value if hasattr(node_type, "value") else str(node_type)

    def _position_value(self, value: Any) -> float:
        return float(value) if value is not None else 0.0

    def _parse_uuid(self, value: Any) -> UUID | None:
        if value is None:
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None
