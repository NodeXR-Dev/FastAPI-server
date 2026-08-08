# app/converter/graph_converter.py

from uuid import UUID

from app.model.graph import Node, Edge
from app.schema.graph.response import (
    NodeGraphResponse,
    SubGraphResponse,
    GraphNodeResponse,
    GraphEdgeResponse,
)


class GraphConverter:

    def to_node_graph_response(
        self,
        *,
        room_id: UUID,
        nodes: list[Node],
        edges: list[Edge],
        graph_version: int,
    ) -> NodeGraphResponse:
        """
        전체 노드/엣지를 sub_graph 단위로 묶어 응답한다.

        NodeGraphResponse 는 graph(단일 flat graph) 대신 sub_graphs 목록을 갖는다.
        (GraphRestoreResponse 와 같은 구조 — 클라이언트는 서브그래프의 root_node_id 로
        PROPERTY→PART 연결을 만든다)
        """

        nodes_by_sub_graph: dict[UUID, list[Node]] = {}
        sub_graph_id_by_node_id: dict[UUID, UUID] = {}
        for node in nodes:
            if node.sub_graph_id is None:
                continue
            nodes_by_sub_graph.setdefault(node.sub_graph_id, []).append(node)
            sub_graph_id_by_node_id[node.node_id] = node.sub_graph_id

        edges_by_sub_graph: dict[UUID, list[Edge]] = {
            sub_graph_id: [] for sub_graph_id in nodes_by_sub_graph
        }
        for edge in edges:
            # 엣지에 sub_graph_id 가 없으면 양 끝 노드로 유추한다.
            resolved = getattr(edge, "sub_graph_id", None)
            if resolved is None:
                resolved = sub_graph_id_by_node_id.get(
                    edge.from_node_id,
                ) or sub_graph_id_by_node_id.get(edge.to_node_id)

            if resolved in edges_by_sub_graph:
                edges_by_sub_graph[resolved].append(edge)

        sub_graphs = [
            SubGraphResponse(
                sub_graph_id=sub_graph_id,
                root_node_id=self._resolve_root_node_id(
                    nodes_by_sub_graph[sub_graph_id],
                ),
                nodes=[
                    self._to_node_response(node)
                    for node in nodes_by_sub_graph[sub_graph_id]
                ],
                edges=[
                    self._to_edge_response(edge)
                    for edge in edges_by_sub_graph[sub_graph_id]
                ],
            )
            for sub_graph_id in nodes_by_sub_graph
        ]

        return NodeGraphResponse(
            room_id=room_id,
            graph_version=graph_version,
            sub_graphs=sub_graphs,
        )

    # 서브그래프 안에서 부모가 없는(또는 부모가 바깥에 있는) 노드가 root 다.
    @staticmethod
    def _resolve_root_node_id(nodes: list[Node]) -> UUID | None:
        node_ids = {node.node_id for node in nodes}
        for node in nodes:
            if node.parent_node_id is None or node.parent_node_id not in node_ids:
                return node.node_id
        return nodes[0].node_id if nodes else None

    @staticmethod
    def _to_node_response(node: Node) -> GraphNodeResponse:
        return GraphNodeResponse(
            node_id=node.node_id,
            type=node.node_type,
            node_text=node.node_text,
            position=[
                node.position_x if node.position_x is not None else 0.0,
                node.position_y if node.position_y is not None else 0.0,
                node.position_z if node.position_z is not None else 0.0,
            ],
            parent_node_id=node.parent_node_id,
            data={},
        )

    @staticmethod
    def _to_edge_response(edge: Edge) -> GraphEdgeResponse:
        return GraphEdgeResponse(
            edge_id=edge.edge_id,
            from_node_id=edge.from_node_id,
            to_node_id=edge.to_node_id,
            label=edge.label,
        )
