from collections import defaultdict
from uuid import UUID

from sqlalchemy.orm import Session

from app.repository.feature_repository import FeatureRepository
from app.repository.graph_repository import GraphRepository
from app.repository.room_repository import RoomRepository
from app.schema.generation.request import Connection2D
from app.schema.generation.generation_result import (
    ConnectionPromptInfo,
    PromptContext,
)

class PromptContextBuilder:
    def __init__(
        self,
        *,
        feature_repository: FeatureRepository | None = None,
        room_repository: RoomRepository | None = None,
        graph_repository: GraphRepository | None = None,
    ) -> None:
        self.feature_repository = feature_repository or FeatureRepository()
        self.room_repository = room_repository or RoomRepository()
        self.graph_repository = graph_repository or GraphRepository()

    def capture_snapshot_context(
        self,
        *,
        db: Session,
        room_id: UUID,
        connections: list[Connection2D],
    ) -> dict:
        return {
            "topic": self.room_repository.find_room_topic(
                db=db,
                room_id=room_id,
            ),
            "features": self.feature_repository.find_feature_texts(
                db=db,
                room_id=room_id,
            ),
            "connections": [
                connection.model_dump(mode="json")
                for connection in connections
            ],
        }

    def build_from_snapshot(
        self,
        *,
        db: Session,
        room_id: UUID,
        graph_snapshot_id: UUID,
        expected_connections: list[Connection2D] | None = None,
    ) -> PromptContext:
        graph_snapshot = self.graph_repository.find_graph_snapshot_by_id(
            db=db,
            room_id=room_id,
            graph_snapshot_id=graph_snapshot_id,
        )
        if graph_snapshot is None:
            raise ValueError("Generation Input Snapshot을 찾을 수 없습니다.")

        snapshot_data = self.graph_repository.load_snapshot_data(
            graph_snapshot=graph_snapshot,
        )
        generation_context = snapshot_data.get("_generation_context")
        if not isinstance(generation_context, dict):
            raise ValueError("Generation Input Snapshot에 Prompt Context가 없습니다.")

        snapshot_connections = [
            Connection2D.model_validate(connection)
            for connection in generation_context.get("connections", [])
        ]
        if (
            expected_connections is not None
            and snapshot_connections != expected_connections
        ):
            raise ValueError("요청 Connection과 Input Snapshot이 일치하지 않습니다.")

        node_by_id: dict[UUID, tuple[dict, UUID | None]] = {}
        # PART 는 sub_graph 에 속하지 않아 snapshot 의 part_nodes 에 따로 실린다.
        # 이걸 같이 넣지 않으면 Connection 의 part_node_id 를 찾지 못해
        # 연결을 건 생성이 항상 실패한다.
        for part_node in snapshot_data.get("part_nodes", []):
            node_by_id[UUID(str(part_node["node_id"]))] = (part_node, None)

        for sub_graph in snapshot_data.get("sub_graphs", []):
            sub_graph_id_value = sub_graph.get("sub_graph_id")
            sub_graph_id = (
                UUID(str(sub_graph_id_value))
                if sub_graph_id_value is not None
                else None
            )
            for node in sub_graph.get("nodes", []):
                node_id = UUID(str(node["node_id"]))
                node_by_id[node_id] = (node, sub_graph_id)

        grouped_connections: dict[
            UUID | None,
            list[ConnectionPromptInfo],
        ] = defaultdict(list)
        for connection in snapshot_connections:
            part_entry = node_by_id.get(connection.part_node_id)
            target_entry = node_by_id.get(connection.node_id)
            if part_entry is None or target_entry is None:
                raise ValueError(
                    "Input Snapshot에서 생성 Connection의 Node를 찾을 수 없습니다."
                )

            target_node, sub_graph_id = target_entry
            node_chain_texts = self._build_snapshot_node_chain_texts(
                target_node=target_node,
                node_by_id=node_by_id,
            )
            grouped_connections[sub_graph_id].append(
                ConnectionPromptInfo(
                    part_node_id=connection.part_node_id,
                    part_node_text=part_entry[0].get("node_text") or "",
                    node_id=connection.node_id,
                    node_chain_texts=node_chain_texts,
                    sub_graph_id=sub_graph_id,
                )
            )

        return PromptContext(
            room_id=room_id,
            topic=str(generation_context.get("topic") or ""),
            features=[
                str(feature)
                for feature in generation_context.get("features", [])
                if feature
            ],
            grouped_connections=dict(grouped_connections),
        )

    @staticmethod
    def _build_snapshot_node_chain_texts(
        *,
        target_node: dict,
        node_by_id: dict[UUID, tuple[dict, UUID | None]],
    ) -> list[str]:
        chain: list[str] = []
        current = target_node
        visited_node_ids: set[UUID] = set()

        while current is not None:
            current_node_id = UUID(str(current["node_id"]))
            if current_node_id in visited_node_ids:
                raise ValueError("Input Snapshot의 Node 부모 관계에 cycle이 있습니다.")
            visited_node_ids.add(current_node_id)

            node_text = current.get("node_text")
            if node_text:
                chain.append(str(node_text))

            parent_node_id = current.get("parent_node_id")
            if parent_node_id is None:
                break
            parent_entry = node_by_id.get(UUID(str(parent_node_id)))
            if parent_entry is None:
                break
            current = parent_entry[0]

        chain.reverse()
        return chain
