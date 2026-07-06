from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.response import success_response
from app.db.session import SessionLocal, get_db
from app.repository.graph_repository import GraphRepository
from app.schema.generation.request import (
    Connection2D,
    Generate2DGraphRequest,
    Generate2DFeatureRequest,
    Generate3DRequest,
)
from app.schema.generation.ws_event_generation_payload import (
    Image2DAssetPayload,
    Model3DAssetPayload,
)
from app.schema.websocket.ws_event import (
    Image2DGeneratedWSEvent,
)
from app.service.generation.image_2d_generation_service import Image2DGenerationService
from app.service.generation.image_2d_feature_generation_service import Image2DFeatureGenerationService
from app.service.generation.model_3d_generation_service import Model3DGenerationService
from app.service.websocket.connection_manager import room_ws_manager

logger = get_logger(__name__)

router = APIRouter(
    tags=["2D"]
)

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
            _run_2d_generation_task,
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
        _run_2d_feature_generation_task,
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
    
async def _run_2d_feature_generation_task(
    *,
    room_id: UUID,
    user_id: UUID,
) -> None:
    logger.info(
        "[2d_feature_generation_task_started] room_id=%s | user_id=%s",
        room_id,
        user_id
    )

    db = SessionLocal()

    try:
        service = Image2DFeatureGenerationService(
            db=db,
        )

        result = await service.generate(
            room_id=room_id,
            user_id=user_id,
        )

        ws_event = Image2DGeneratedWSEvent(
            room_id=room_id,
            user_id=user_id,
            payload=Image2DAssetPayload(
                asset_id=result.asset_id,
                mime_type=result.mime_type,
                width=result.width,
                height=result.height,
                img_url=result.img_url,
            ),
        )

        #await room_ws_manager.broadcast_to_room(
        #    room_id=room_id,
        #    message=ws_event.model_dump(mode="json"),
        #)
        
        await room_ws_manager.send_to_user(
            room_id=room_id,
            user_id=user_id,
            message=ws_event.model_dump(mode="json"),
        )

        logger.info(
            "[2d_feature_generation_task_completed] room_id=%s | asset_id=%s",
            room_id,
            result.asset_id,
        )

    except Exception as e:
        db.rollback()

        logger.exception(
            "[2d_feature_generation_task_failed] room_id=%s | error=%s",
            room_id,
            str(e),
        )
        
        await room_ws_manager.broadcast_to_room(
            room_id=room_id,
            message=ws_event.model_dump(mode="json"),
        )

    finally:
        db.close()

        logger.info(
            "[2d_feature_generation_task_db_closed] room_id=%s",
            room_id,
        )

async def _run_2d_generation_task(
    *,
    room_id: UUID,
    user_id: UUID,
    graph_snapshot_id: UUID,
    connections: list[Connection2D],
) -> None:
    logger.info(
        "[2d_generation_task_started] room_id=%s | user_id=%s | graph_snapshot_id=%s | connection_count=%s",
        room_id,
        user_id,
        graph_snapshot_id,
        len(connections),
    )

    db = SessionLocal()

    try:
        service = Image2DGenerationService(
            db=db,
        )

        result = await service.generate(
            room_id=room_id,
            user_id=user_id,
            graph_snapshot_id=graph_snapshot_id,
            connections=connections,
        )

        ws_event = Image2DGeneratedWSEvent(
            room_id=room_id,
            user_id=user_id,
            payload=Image2DAssetPayload(
                asset_id=result.asset_id,
                mime_type=result.mime_type,
                width=result.width,
                height=result.height,
                img_url=result.img_url,
            ),
        )

        await room_ws_manager.broadcast_to_room(
            room_id=room_id,
            message=ws_event.model_dump(mode="json"),
        )

        logger.info(
            "[2d_generation_task_completed] room_id=%s | graph_snapshot_id=%s | asset_id=%s",
            room_id,
            graph_snapshot_id,
            result.asset_id,
        )

    except Exception as e:
        logger.exception(
            "[2d_generation_task_failed] room_id=%s | graph_snapshot_id=%s | error=%s",
            room_id,
            graph_snapshot_id,
            str(e),
        )

        await room_ws_manager.broadcast_to_room(
            room_id=room_id,
            message=ws_event.model_dump(mode="json"),
        )

    finally:
        db.close()

        logger.info(
            "[2d_generation_task_db_closed] room_id=%s | graph_snapshot_id=%s",
            room_id,
            graph_snapshot_id,
        )