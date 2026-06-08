from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks

from app.core.logger import get_logger
from app.core.response.response import success_response
from app.core.response.code import ResponseCode
from app.websocket.connection_manager import room_ws_manager

from app.schema.generation.generation_request import (
    Generate2DRequest,
    Generate3DRequest,
)
from app.schema.generation.ws_event_generation_payload import (
    Image2DAssetPayload,
    Model3DAssetPayload,
)
from app.schema.websocket.ws_event import (
    Image2DGeneratedWSEvent,
    Model3DGeneratedWSEvent,
)

from app.service.generation.image_2d_generation_service import Image2DGenerationService
from app.service.generation.model_3d_generation_service import Model3DGenerationService

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


@router.post("/2d/generate")
async def request_2d_generate(
    request: Generate2DRequest,
    background_tasks: BackgroundTasks,
):
    job_id = uuid4()

    logger.info(
        "[2d_generate_requested] room_id=%s | user_id=%s | job_id=%s",
        request.room_id,
        request.user_id,
        job_id,
    )

    background_tasks.add_task(
        _run_2d_generation_task,
        room_id=request.room_id,
        user_id=request.user_id,
        job_id=job_id,
        prompt=request.prompt,
        target_node_id=request.target_node_id,
    )

    return success_response(
        code=ResponseCode.IMG202,
        message="2D 이미지 생성 요청이 접수되었습니다.",
        result=GenerationAcceptedResult(job_id=job_id).model_dump(mode="json"),
    )


@router.post("/3d/generate")
async def request_3d_generate(
    request: Generate3DRequest,
    background_tasks: BackgroundTasks,
):
    job_id = uuid4()

    logger.info(
        "[3d_generate_requested] room_id=%s | user_id=%s | job_id=%s",
        request.room_id,
        request.user_id,
        job_id,
    )

    background_tasks.add_task(
        _run_3d_generation_task,
        room_id=request.room_id,
        user_id=request.user_id,
        job_id=job_id,
        prompt=request.prompt,
        source_asset_id=request.source_asset_id,
        target_node_id=request.target_node_id,
    )

    return success_response(
        code=ResponseCode.MODEL202,
        message="3D 모델 생성 요청이 접수되었습니다.",
        result=GenerationAcceptedResult(job_id=job_id).model_dump(mode="json"),
    )


async def _run_2d_generation_task(
    *,
    room_id: UUID,
    user_id: UUID,
    job_id: UUID,
    prompt: str,
    target_node_id: UUID | None,
):
    logger.info(
        "[2d_generation_started] room_id=%s | user_id=%s | job_id=%s",
        room_id,
        user_id,
        job_id,
    )

    try:
        service = Image2DGenerationService()

        result = await service.generate(
            room_id=room_id,
            user_id=user_id,
            job_id=job_id,
            prompt=prompt,
            target_node_id=target_node_id,
        )

        ws_event = Image2DGeneratedWSEvent(
            room_id=room_id,
            user_id=user_id,
            payload=GeneratedAssetEventPayload(
                job_id=job_id,
                target_node_id=target_node_id,
                asset=Image2DAssetPayload(
                    asset_id=result["asset_id"],
                    mime_type=result["mime_type"],
                    width=result.get("width"),
                    height=result.get("height"),
                    img_url=result["img_url"],
                ),
            ),
        )

        await room_ws_manager.broadcast_to_room(
            room_id=room_id,
            message=ws_event.model_dump(mode="json"),
        )

        logger.info(
            "[2d_generation_completed] room_id=%s | user_id=%s | job_id=%s | asset_id=%s",
            room_id,
            user_id,
            job_id,
            result["asset_id"],
        )

    except Exception as e:
        logger.exception(
            "[2d_generation_failed] room_id=%s | user_id=%s | job_id=%s | error=%s",
            room_id,
            user_id,
            job_id,
            str(e),
        )

        ws_event = Image2DGenerationFailedWSEvent(
            room_id=room_id,
            user_id=user_id,
            payload=GenerationFailedPayload(
                job_id=job_id,
                target_node_id=target_node_id,
                code="IMG500",
                message="2D 이미지 생성에 실패했습니다.",
                reason=str(e),
            ),
        )

        await room_ws_manager.broadcast_to_room(
            room_id=room_id,
            message=ws_event.model_dump(mode="json"),
        )


async def _run_3d_generation_task(
    *,
    room_id: UUID,
    user_id: UUID,
    job_id: UUID,
    prompt: str,
    source_asset_id: UUID | None,
    target_node_id: UUID | None,
):
    logger.info(
        "[3d_generation_started] room_id=%s | user_id=%s | job_id=%s",
        room_id,
        user_id,
        job_id,
    )

    try:
        service = Model3DGenerationService()

        result = await service.generate(
            room_id=room_id,
            user_id=user_id,
            job_id=job_id,
            prompt=prompt,
            source_asset_id=source_asset_id,
            target_node_id=target_node_id,
        )

        ws_event = Model3DGeneratedWSEvent(
            room_id=room_id,
            user_id=user_id,
            payload=GeneratedAssetEventPayload(
                job_id=job_id,
                target_node_id=target_node_id,
                asset=Model3DAssetPayload(
                    asset_id=result["asset_id"],
                    mime_type=result["mime_type"],
                    model_url=result["model_url"],
                    thumbnail_url=result.get("thumbnail_url"),
                ),
            ),
        )

        await room_ws_manager.broadcast_to_room(
            room_id=room_id,
            message=ws_event.model_dump(mode="json"),
        )

        logger.info(
            "[3d_generation_completed] room_id=%s | user_id=%s | job_id=%s | asset_id=%s",
            room_id,
            user_id,
            job_id,
            result["asset_id"],
        )

    except Exception as e:
        logger.exception(
            "[3d_generation_failed] room_id=%s | user_id=%s | job_id=%s | error=%s",
            room_id,
            user_id,
            job_id,
            str(e),
        )

        ws_event = Model3DGenerationFailedWSEvent(
            room_id=room_id,
            user_id=user_id,
            payload=GenerationFailedPayload(
                job_id=job_id,
                target_node_id=target_node_id,
                code="MODEL500",
                message="3D 모델 생성에 실패했습니다.",
                reason=str(e),
            ),
        )

        await room_ws_manager.broadcast_to_room(
            room_id=room_id,
            message=ws_event.model_dump(mode="json"),
        )