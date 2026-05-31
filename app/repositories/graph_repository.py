# app/repositories/graph_repository.py

import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.graph import SubGraph, Node, Edge, GraphSnapshot
from app.models.graph import NodeUtteranceLink
from app.schemas.graph.response import GraphResponse


class GraphRepository:
    def save_graph_from_response(
        self,
        db: Session,
        room_id: UUID,
        utterance_id: UUID,
        graph: GraphResponse,
    ):
        sub_graph = SubGraph(
            room_id=room_id,
        )
        db.add(sub_graph)
        db.flush()

        node_id_map = {}
        saved_nodes = []

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

            node_id_map[node_response.node_id] = node.node_id
            saved_nodes.append(node)

            db.add(
                NodeUtteranceLink(
                    node_id=node.node_id,
                    utterance_id=utterance_id,
                )
            )

        saved_edges = []

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

        snapshot_data = graph.model_dump(mode="json")

        graph_snapshot = GraphSnapshot(
            room_id=room_id,
            snapshot_data=json.dumps(snapshot_data, ensure_ascii=False),
            version=graph.graph_version,
        )

        db.add(graph_snapshot)
        db.flush()

        return sub_graph, graph_snapshot, saved_nodes, saved_edges