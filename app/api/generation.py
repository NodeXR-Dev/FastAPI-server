from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException
from app.core.response.response import success_response
from app.db.session import get_db
from app.repository.graph_repository import GraphRepository
from app.schema.generation.request import (
    Generate2DFeatureRequest,
    Generate2DGraphRequest,
    Generate3DRequest,
)
from app.schema.generation.color_change_request import (
    ColorChangeMetadataRequest,
    ColorChangeRequest,
)
from app.service.generation.image_2d_color_change_service import (
    Image2DColorChangeService,
)
from app.service.generation.image_2d_generation_task_service import (
    Image2DGenerationTaskService,
)
from app.service.generation.prompt_context_builder import PromptContextBuilder
from app.service.generation.model_3d_generation_service import (
    Model3DGenerationService,
)

logger = get_logger(__name__)

router = APIRouter(
    tags=["2D"]
)

image_2d_generation_task_service = Image2DGenerationTaskService()
image_2d_color_change_service = Image2DColorChangeService()
prompt_context_builder = PromptContextBuilder()
model_3d_generation_service = Model3DGenerationService()


@router.post(
    "/3d/generate",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["3D"],
)
def request_3d_generate(
    request: Generate3DRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    logger.info(
        "[3d_generation_requested] room_id=%s | user_id=%s | job_id=%s | source_asset_id=%s",
        request.room_id,
        request.user_id,
        request.job_id,
        request.asset_id,
    )
    model_3d_generation_service.validate_request(
        db=db,
        request=request,
    )
    background_tasks.add_task(
        model_3d_generation_service.run,
        room_id=request.room_id,
        user_id=request.user_id,
        job_id=request.job_id,
        source_asset_id=request.asset_id,
    )
    logger.info(
        "[3d_generation_task_registered] room_id=%s | user_id=%s | job_id=%s | source_asset_id=%s",
        request.room_id,
        request.user_id,
        request.job_id,
        request.asset_id,
    )
    return success_response(
        code=ResponseCode.MODEL_3D200,
        result={"job_id": str(request.job_id)},
    )


@router.post(
    "/2d/color_change",
    status_code=status.HTTP_202_ACCEPTED,
)
def request_2d_color_change(
    room_id: Annotated[UUID, Form()],
    user_id: Annotated[UUID, Form()],
    job_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
    asset_id: Annotated[UUID, Form()],
    metadata: Annotated[str, Form()],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    guide_image_bytes = file.file.read()

    try:
        parsed_metadata = ColorChangeMetadataRequest.model_validate_json(metadata)
    except ValidationError as exc:
        raise BadRequestException(
            code=ResponseCode.COLOR_CHANGE400,
            message="metadata는 유효한 JSON 형식이어야 합니다.",
        ) from exc

    request = ColorChangeRequest(
        room_id=room_id,
        user_id=user_id,
        job_id=job_id,
        asset_id=asset_id,
        metadata=parsed_metadata,
    )
    graph_snapshot_id = image_2d_color_change_service.validate_request(
        db=db,
        request=request,
        guide_image_bytes=guide_image_bytes,
        upload_content_type=file.content_type,
    )

    background_tasks.add_task(
        image_2d_generation_task_service.generate_color_change,
        room_id=room_id,
        user_id=user_id,
        job_id=job_id,
        source_asset_id=asset_id,
        graph_snapshot_id=graph_snapshot_id,
        guide_image_bytes=guide_image_bytes,
        metadata=parsed_metadata,
    )

    return success_response(
        code=ResponseCode.COLOR_CHANGE201,
        result={"job_id": str(job_id)},
    )


@router.post("/2d/generate/graph")
async def request_2d_generate(
    request: Generate2DGraphRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    logger.info(
        "[2d_generate_requested] room_id=%s | user_id=%s | job_id=%s | connection_count=%s",
        request.room_id,
        request.user_id,
        request.job_id,
        len(request.connections),
    )

    try:
        graph_repository = GraphRepository()
        generation_context = prompt_context_builder.capture_snapshot_context(
            db=db,
            room_id=request.room_id,
            connections=request.connections,
        )

        graph_snapshot = graph_repository.create_graph_snapshot_from_current_graph(
            db=db,
            room_id=request.room_id,
            generation_context=generation_context,
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
            job_id=request.job_id,
            graph_snapshot_id=graph_snapshot.graph_snapshot_id,
            connections=request.connections,
        )

        logger.info(
            "[2d_generate_task_registered] room_id=%s | user_id=%s | job_id=%s | graph_snapshot_id=%s",
            request.room_id,
            request.user_id,
            request.job_id,
            graph_snapshot.graph_snapshot_id,
        )

        return success_response(
            code=ResponseCode.IMG202,
            message="2D 이미지 생성 요청이 접수되었습니다.",
            result={"job_id": str(request.job_id)},
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
        "[2d_feature_generate_requested] room_id=%s | user_id=%s | job_id=%s",
        request.room_id,
        request.user_id,
        request.job_id,
    )

    background_tasks.add_task(
        image_2d_generation_task_service.generate_from_features,
        room_id=request.room_id,
        user_id=request.user_id,
        job_id=request.job_id,
    )

    logger.info(
        "[2d_feature_generate_task_registered] room_id=%s | user_id=%s | job_id=%s",
        request.room_id,
        request.user_id,
        request.job_id,
    )

    return success_response(
        code=ResponseCode.IMG202,
        message="Feature 기반 2D 이미지 생성 요청이 접수되었습니다.",
        result={"job_id": str(request.job_id)},
    )
