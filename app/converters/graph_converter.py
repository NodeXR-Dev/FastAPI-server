from uuid import UUID

from app.schemas.graph.response import (
    GraphNodeResponse,
    GraphEdgeResponse,
    GraphResponse,
    NodeGraphResponse,
)


class GraphConverter:
    def to_node_graph_response(
        self,
        room_id: UUID,
        nodes,
        edges,
        graph_version: int = 1,
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
                            node.position_x,
                            node.position_y,
                            node.position_z,
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
            )
        )