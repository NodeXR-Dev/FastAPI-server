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

