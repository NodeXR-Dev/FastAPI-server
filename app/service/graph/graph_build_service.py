# app/services/graph/graph_build_service.py

import time
from uuid import UUID, uuid4

from app.core.logger import get_logger
from app.core.performance import performance_tracker
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException, ServerException
from app.model.enum import NodeType
from app.schema.graph.response import (
    GraphNodeResponse,
    GraphEdgeResponse,
    GraphResponse,
)
from app.schema.generation.node_keyword_response import KeywordExtractResult

logger = get_logger(__name__)


class GraphBuildService:
    def build_graph_from_extraction(
        self,
        extraction: KeywordExtractResult,
        parent_node_id: UUID | None = None,
    ) -> GraphResponse:
        stage = "service_graph_build_graph_from_extraction"
        start_time = time.perf_counter()

        logger.info(
            "[service_graph_build_graph_from_extraction] start | node_count=%s | parent_node_id=%s",
            len(extraction.nodes) if extraction is not None else None,
            parent_node_id,
        )

        try:
            if extraction is None or not extraction.nodes:
                raise BadRequestException(
                    code=ResponseCode.BTUTT400,
                    message="그래프를 생성할 노드가 없습니다.",
                )

            nodes: list[GraphNodeResponse] = []
            edges: list[GraphEdgeResponse] = []

            node_id_by_text = {}

            for extracted_node in extraction.nodes:
                node_id = uuid4()

                node_id_by_text[extracted_node.node_text] = node_id

                nodes.append(
                    GraphNodeResponse(
                        node_id=node_id,
                        type=NodeType.PROPERTY,
                        node_text=extracted_node.node_text,
                        position=[],
                        parent_node_id=parent_node_id,
                        data={},
                    )
                )

            if parent_node_id is not None:
                for parent_edge in extraction.parent_edges:
                    to_node_id = node_id_by_text.get(parent_edge.to_node_text)

                    if to_node_id is None:
                        continue

                    edges.append(
                        GraphEdgeResponse(
                            edge_id=uuid4(),
                            from_node_id=parent_node_id,
                            to_node_id=to_node_id,
                            label=parent_edge.label,
                        )
                    )

            for internal_edge in extraction.internal_edges:
                from_node_id = node_id_by_text.get(internal_edge.from_node_text)
                to_node_id = node_id_by_text.get(internal_edge.to_node_text)

                if from_node_id is None or to_node_id is None:
                    continue

                edges.append(
                    GraphEdgeResponse(
                        edge_id=uuid4(),
                        from_node_id=from_node_id,
                        to_node_id=to_node_id,
                        label=internal_edge.label,
                    )
                )

            graph = GraphResponse(
                graph_version=1,
                nodes=nodes,
                edges=edges,
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            avg_ms = performance_tracker.record(stage, elapsed_ms)

            logger.info(
                "[graph_build] done | elapsed_ms=%.2f | avg_ms=%.2f | node_count=%s | edge_count=%s",
                elapsed_ms,
                avg_ms,
                len(nodes),
                len(edges),
            )

            return graph

        except BadRequestException:
            raise

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[graph_build] failed | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise ServerException(
                code=ResponseCode.BTUTT500,
                message="그래프 생성 중 서버 오류가 발생했습니다.",
            )

    def node_positioning(
        self,
        graph: GraphResponse,
        parent_position: list[float] | None = None,
    ) -> GraphResponse:
        """
        Unity에서 보기 좋도록 node 위치를 배치한다.

        배치 규칙:
        1. parent_position이 없으면 root graph로 판단
           - 첫 노드는 (0, 0, 0)
           - 여러 노드는 x축으로 나열

        2. parent_position이 있으면 child graph로 판단
           - parent 아래쪽(y 감소)에 배치
           - 여러 자식 노드는 parent를 중심으로 x축 분산
        """

        stage = "node_positioning"
        start_time = time.perf_counter()

        logger.info(
            "[node_positioning] start | node_count=%s | parent_position=%s",
            len(graph.nodes) if graph is not None else None,
            parent_position,
        )

        try:
            if graph is None or not graph.nodes:
                raise BadRequestException(
                    code=ResponseCode.BTUTT400,
                    message="위치를 배치할 노드가 없습니다.",
                )

            x_spacing = 1.5
            y_spacing = 1.5

            node_count = len(graph.nodes)
            center_index = (node_count - 1) / 2

            # parent_position이 없으면 root graph로 배치
            if parent_position is None:
                for idx, node in enumerate(graph.nodes):
                    node.position = [
                        (idx - center_index) * x_spacing,
                        0.0,
                        0.0,
                    ]

                elapsed_ms = (time.perf_counter() - start_time) * 1000
                avg_ms = performance_tracker.record(stage, elapsed_ms)

                logger.info(
                    "[node_positioning] done_root | elapsed_ms=%.2f | avg_ms=%.2f",
                    elapsed_ms,
                    avg_ms,
                )

                return graph

            # parent_position 형식 검증
            if len(parent_position) < 3:
                raise BadRequestException(
                    code=ResponseCode.BTUTT400,
                    message="parent_position은 [x, y, z] 형태여야 합니다.",
                )

            parent_x = float(parent_position[0])
            parent_y = float(parent_position[1])
            parent_z = float(parent_position[2])

            # parent 아래쪽에 child nodes 배치
            for idx, node in enumerate(graph.nodes):
                node.position = [
                    parent_x + ((idx - center_index) * x_spacing),
                    parent_y - y_spacing,
                    parent_z,
                ]

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            avg_ms = performance_tracker.record(stage, elapsed_ms)

            logger.info(
                "[node_positioning] done_child | elapsed_ms=%.2f | avg_ms=%.2f",
                elapsed_ms,
                avg_ms,
            )

            return graph

        except BadRequestException:
            raise

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[node_positioning] failed | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise ServerException(
                code=ResponseCode.BTUTT500,
                message="노드 위치 배치 중 서버 오류가 발생했습니다.",
            )