# app/services/utterance/button_utterance_service.py

import time
import uuid

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.performance import performance_tracker
from app.core.response.code import ResponseCode
from app.core.response.exceptions import (
    BadRequestException,
    NotFoundException,
    ServerException,
)
from app.db.session import SessionLocal
from app.model.enum import UtteranceState
from app.model.graph import Node
from app.schema.utterance.request import CreateNodeUtteranceRequest
from app.schema.graph.response import NodeGraphResponse

from app.service.utterance.text_preprocess_service import TextPreprocessService
from app.service.utterance.embedding_service import EmbeddingService
from app.service.utterance.keyword_service import KeywordService
from app.service.graph.graph_build_service import GraphBuildService

from app.repository.utterance_repository import UtteranceRepository
from app.repository.graph_repository import GraphRepository
from app.converter.graph_converter import GraphConverter

logger = get_logger(__name__)


class ButtonUtteranceService:
    def __init__(self):
        self.text_preprocess_service = TextPreprocessService()
        self.embedding_service = EmbeddingService()
        self.keyword_service = KeywordService()
        self.graph_build_service = GraphBuildService()

        self.utterance_repository = UtteranceRepository()
        self.graph_repository = GraphRepository()

        self.graph_converter = GraphConverter()

    def create_node_graph_from_utterance(
        self,
        db: Session,
        request: CreateNodeUtteranceRequest,
        background_tasks: BackgroundTasks,
    ) -> NodeGraphResponse:
        stage = "service_utterance_create_node_graph_from_utterance"
        start_time = time.perf_counter()

        logger.info(
            "[service_utterance_create_node_graph_from_utterance] start | room_id=%s | user_id=%s | parent_node_id=%s",
            request.room_id,
            request.user_id,
            request.parent_node_id,
        )

        try:
            # 1. original_text만 우선 저장
            utterance = self.utterance_repository.create(
                db=db,
                room_id=request.room_id,
                user_id=request.user_id,
                original_text=request.utterance,
                state=UtteranceState.NOREFLECT,
            )

            # 2. keyword 추출에 필요하므로 normalized_text 계산은 즉시 수행
            normalized_text = self.text_preprocess_service.utterance_preprocess(
                request.utterance
            )

            # 3. keyword 추출
            parent_node_text: str | None = None

            if request.parent_node_id is not None:
                parent_node = (
                    db.query(Node)
                    .filter(Node.node_id == request.parent_node_id)
                    .first()
                )

                if parent_node is None:
                    raise NotFoundException(
                        code=ResponseCode.NODE404,
                        message="부모 노드를 찾을 수 없습니다.",
                    )

                parent_node_text = parent_node.node_text

            extraction = self.keyword_service.keyword_extract(
                utterance=normalized_text,
                parent_node_text=parent_node_text,
            )
            
            # 4. graph 생성
            graph = self.graph_build_service.build_graph_from_extraction(
                extraction=extraction,
                parent_node_id=request.parent_node_id,
            )

            graph = self.graph_build_service.node_positioning(
                graph=graph,
                parent_position=request.parent_node_position,
            )

            # 5. graph 저장
            sub_graph, graph_snapshot, saved_nodes, saved_edges, all_nodes, all_edges = (
                self.graph_repository.save_graph_from_response(
                    db=db,
                    room_id=request.room_id,
                    utterance_id=utterance.utterance_id,
                    graph=graph,
                )
            )

            # 6. graph까지는 먼저 commit
            db.commit()

            for node in all_nodes:
                db.refresh(node)

            for edge in all_edges:
                db.refresh(edge)

            db.refresh(sub_graph)
            db.refresh(graph_snapshot)
            db.refresh(utterance)

            # 7. normalized_text 저장 + embedding 계산/저장은 background 처리
            background_tasks.add_task(
                self.update_utterance_normalized_and_embedding_background,
                utterance_id=utterance.utterance_id,
                normalized_text=normalized_text,
            )

            # 8. 전체 그래프 기준 response
            response = self.graph_converter.to_node_graph_response(
                room_id=request.room_id,
                nodes=all_nodes,
                edges=all_edges,
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
                "[service_create_node_graph_from_utterance] failed | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise ServerException(
                code=ResponseCode.BTUTT500,
                message="버튼 발화 기반 노드 그래프 생성 중 서버 오류가 발생했습니다.",
            )

    def update_utterance_normalized_and_embedding_background(
        self,
        *,
        utterance_id: uuid.UUID,
        normalized_text: str,
    ) -> None:
        
        stage = "background_utterance_normalized_embedding_update"
        start_time = time.perf_counter()

        db = SessionLocal()

        logger.info(
            "[background_utterance_normalized_embedding_update] start | utterance_id=%s",
            utterance_id,
        )

        try:
            # background에서 embedding 계산
            embedding = self.embedding_service.embed_text(normalized_text)

            # 같은 utterance row에 normalized_text + embedding update
            utterance = self.utterance_repository.update(
                db=db,
                utterance_id=utterance_id,
                normalized_text=normalized_text,
                embedding=embedding,
            )

            db.commit()

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            avg_ms = performance_tracker.record(stage, elapsed_ms)

            logger.info(
                "[background_utterance_normalized_embedding_update] done | elapsed_ms=%.2f | avg_ms=%.2f | utterance_id=%s",
                elapsed_ms,
                avg_ms,
                utterance.utterance_id if utterance else utterance_id,
            )

        except Exception as e:
            db.rollback()

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[background_utterance_normalized_embedding_update] failed | elapsed_ms=%.2f | utterance_id=%s | error=%s",
                elapsed_ms,
                utterance_id,
                str(e),
            )

        finally:
            db.close()