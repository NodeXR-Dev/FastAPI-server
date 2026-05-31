# app/services/utterances/button_utterance_service.py

import time

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.performance import performance_tracker
from app.core.response.code import ResponseCode
from app.core.response.exceptions import (
    BadRequestException,
    NotFoundException,
    ServerException,
)
from app.models.enums import UtteranceType
from app.schemas.utterance.request import CreateNodeUtteranceRequest
from app.schemas.graph.response import NodeGraphResponse

from app.services.utterances.text_preprocess_service import TextPreprocessService
from app.services.utterances.embedding_service import EmbeddingService
from app.services.utterances.keyword_service import KeywordService
from app.services.graph.graph_build_service import GraphBuildService

from app.repositories.utterance_repository import UtteranceRepository
from app.repositories.episode_repository import EpisodeRepository
from app.repositories.graph_repository import GraphRepository
from app.converters.graph_converter import GraphConverter

logger = get_logger(__name__)


class ButtonUtteranceService:
    def __init__(self):
        self.text_preprocess_service = TextPreprocessService()
        self.embedding_service = EmbeddingService()
        self.keyword_service = KeywordService()
        self.graph_build_service = GraphBuildService()

        self.utterance_repository = UtteranceRepository()
        self.episode_repository = EpisodeRepository()
        self.graph_repository = GraphRepository()

        self.graph_converter = GraphConverter()

    def create_node_graph_from_utterance(
        self,
        db: Session,
        request: CreateNodeUtteranceRequest,
    ) -> NodeGraphResponse:
        stage = "service_button_create_graph"
        start_time = time.perf_counter()

        logger.info(
            "[service_button_create_graph] start | room_id=%s | user_id=%s | parent_node_id=%s",
            request.room_id,
            request.user_id,
            request.parent_node_id,
        )

        try:
            active_episode = self.episode_repository.find_active_by_room_id(
                db=db,
                room_id=request.room_id,
            )

            if active_episode is None:
                raise NotFoundException(
                    code=ResponseCode.BTUTT404,
                    message="현재 회의실에 활성화된 episode가 없습니다.",
                )

            normalized_text = self.text_preprocess_service.utterance_preprocess(
                request.utterance
            )

            embedding = self.embedding_service.embed_text(normalized_text)

            utterance = self.utterance_repository.create(
                db=db,
                room_id=request.room_id,
                user_id=request.user_id,
                episode_id=active_episode.episode_id,
                original_text=request.utterance,
                normalized_text=normalized_text,
                embedding=embedding,
                state=UtteranceType.NOREFLECT,
            )

            extraction = self.keyword_service.keyword_extract(normalized_text)

            graph = self.graph_build_service.build_graph_from_extraction(
                extraction=extraction,
                parent_node_id=request.parent_node_id,
            )

            graph = self.graph_build_service.node_positioning(
                graph = graph,
                parent_position=request.parent_position
            )

            sub_graph, graph_snapshot, saved_nodes, saved_edges = (
                self.graph_repository.save_graph_from_response(
                    db=db,
                    room_id=request.room_id,
                    utterance_id=utterance.utterance_id,
                    graph=graph,
                )
            )

            db.commit()

            for node in saved_nodes:
                db.refresh(node)

            for edge in saved_edges:
                db.refresh(edge)

            db.refresh(sub_graph)
            db.refresh(graph_snapshot)
            db.refresh(utterance)

            response = self.graph_converter.to_node_graph_response(
                room_id=request.room_id,
                nodes=saved_nodes,
                edges=saved_edges,
                graph_version=graph_snapshot.version,
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            avg_ms = performance_tracker.record(stage, elapsed_ms)

            logger.info(
                "[service_button_create_graph] done | elapsed_ms=%.2f | avg_ms=%.2f | utterance_id=%s | sub_graph_id=%s | snapshot_id=%s",
                elapsed_ms,
                avg_ms,
                utterance.utterance_id,
                sub_graph.sub_graph_id,
                graph_snapshot.graph_snapshot_id,
            )

            return response

        except (BadRequestException, NotFoundException, ServerException):
            db.rollback()
            raise

        except Exception as e:
            db.rollback()

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[service_button_create_graph] failed | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise ServerException(
                code=ResponseCode.BTUTT500,
                message="버튼 발화 기반 노드 그래프 생성 중 서버 오류가 발생했습니다.",
            )