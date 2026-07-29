from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.response import success_response
from app.db.session import get_db
from app.repository.graph_repository import GraphRepository
from app.schema.generation.request import (
    Generate2DFeatureRequest,
    Generate2DGraphRequest,
)
from app.service.generation.image_2d_generation_task_service import (
    Image2DGenerationTaskService,
)

logger = get_logger(__name__)

router = APIRouter(
    tags=["2D"]
)

image_2d_generation_task_service = Image2DGenerationTaskService()


@router.post("/2d/generate/graph")
async def request_2d_generate(
    request: Generate2DGraphRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    logger.info(
        "[2d_generate_requested] room_id=%s | user_id=%s | connection_count=%s",
        request.room_id,
        request.user_id,
        len(request.connections),
    )

    try:
        graph_repository = GraphRepository()

        graph_snapshot = graph_repository.create_graph_snapshot_from_current_graph(
            db=db,
            room_id=request.room_id,
        )

        db.commit()

        logger.info(
            "[2d_generate_snapshot_created] room_id=%s | graph_snapshot_id=%s | version=%s",
            request.room_id,
            graph_snapshot.graph_snapshot_id,
            graph_snapshot.version,
        )

        background_tasks.add_task(
            image_2d_generation_task_service.generate_from_graph,
            room_id=request.room_id,
            user_id=request.user_id,
            graph_snapshot_id=graph_snapshot.graph_snapshot_id,
            connections=request.connections,
        )

        logger.info(
            "[2d_generate_task_registered] room_id=%s | user_id=%s | graph_snapshot_id=%s",
            request.room_id,
            request.user_id,
            graph_snapshot.graph_snapshot_id,
        )

        return success_response(
            code=ResponseCode.IMG202,
            message="2D 이미지 생성 요청이 접수되었습니다.",
        )

    except Exception as e:
        db.rollback()

        logger.exception(
            "[2d_generate_request_failed] room_id=%s | error=%s",
            request.room_id,
            str(e),
        )

        raise


@router.post("/2d/generate/feature")
async def request_2d_generate_by_feature(
    request: Generate2DFeatureRequest,
    background_tasks: BackgroundTasks,
):
    logger.info(
        "[2d_feature_generate_requested] room_id=%s | user_id=%s",
        request.room_id,
        request.user_id,
    )

    background_tasks.add_task(
        image_2d_generation_task_service.generate_from_features,
        room_id=request.room_id,
        user_id=request.user_id,
    )

    logger.info(
        "[2d_feature_generate_task_registered] room_id=%s | user_id=%s",
        request.room_id,
        request.user_id,
    )

    return success_response(
        code=ResponseCode.IMG202,
        message="Feature 기반 2D 이미지 생성 요청이 접수되었습니다.",
    )
