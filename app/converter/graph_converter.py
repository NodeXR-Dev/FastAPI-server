# app/converter/graph_converter.py

from uuid import UUID

from app.model.graph import Node, Edge
from app.schema.graph.response import (
    NodeGraphResponse,
    GraphResponse,
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

        return NodeGraphResponse(
            room_id=room_id,
            graph=GraphResponse(
                graph_version=graph_version,
                nodes=[
                    GraphNodeResponse(
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
                    for node in nodes
                ],
                edges=[
                    GraphEdgeResponse(
                        edge_id=edge.edge_id,
                        from_node_id=edge.from_node_id,
                        to_node_id=edge.to_node_id,
                        label=edge.label,
                    )
                    for edge in edges
                ],
            ),
        )