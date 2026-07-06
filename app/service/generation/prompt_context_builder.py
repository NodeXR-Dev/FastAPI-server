from collections import defaultdict
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.repository.feature_repository import FeatureRepository
from app.repository.graph_repository import GraphRepository
from app.repository.room_repository import RoomRepository
from app.schema.generation.request import Connection2D
from app.schema.generation.generation_result import (
    ConnectionPromptInfo,
    PromptContext,
)

logger = get_logger(__name__)


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

    def build(
        self,
        *,
        db: Session,
        room_id: UUID,
        connections: list[Connection2D],
    ) -> PromptContext:
        logger.info(
            "[prompt_context_build_started] room_id=%s | connection_count=%s",
            room_id,
            len(connections),
        )

        topic = self.room_repository.find_room_topic(
            db=db,
            room_id=room_id,
        )

        features = self.feature_repository.find_feature_texts(
            db=db,
            room_id=room_id,
        )

        grouped_connections: dict[UUID | None, list[ConnectionPromptInfo]] = defaultdict(list)

        for connection in connections:
            logger.info(
                "[prompt_context_connection_started] room_id=%s | part_node_id=%s | node_id=%s",
                room_id,
                connection.part_node_id,
                connection.node_id,
            )

            part_node = self.graph_repository.find_active_node_by_id(
                db=db,
                room_id=room_id,
                node_id=connection.part_node_id,
            )

            if part_node is None:
                raise ValueError(
                    f"part_node를 찾을 수 없습니다. part_node_id={connection.part_node_id}"
                )

            ancestor_chain = self.graph_repository.find_active_ancestor_chain_to_root(
                db=db,
                room_id=room_id,
                node_id=connection.node_id,
            )

            if not ancestor_chain:
                raise ValueError(
                    f"node_id 기준 부모 체인을 찾을 수 없습니다. node_id={connection.node_id}"
                )

            target_node = ancestor_chain[-1]
            sub_graph_id = target_node.sub_graph_id

            node_chain_texts = [
                node.node_text
                for node in ancestor_chain
                if node.node_text
            ]

            grouped_connections[sub_graph_id].append(
                ConnectionPromptInfo(
                    part_node_id=connection.part_node_id,
                    part_node_text=part_node.node_text or "",
                    node_id=connection.node_id,
                    node_chain_texts=node_chain_texts,
                    sub_graph_id=sub_graph_id,
                )
            )

            logger.info(
                "[prompt_context_connection_completed] room_id=%s | sub_graph_id=%s | chain_length=%s",
                room_id,
                sub_graph_id,
                len(node_chain_texts),
            )

        context = PromptContext(
            room_id=room_id,
            topic=topic,
            features=features,
            grouped_connections=dict(grouped_connections),
        )

        logger.info(
            "[prompt_context_build_completed] room_id=%s | feature_count=%s | sub_graph_count=%s",
            room_id,
            len(features),
            len(grouped_connections),
        )

        return context