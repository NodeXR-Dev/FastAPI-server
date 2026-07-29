from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.db.session import SessionLocal
from app.schema.generation.generation_result import Generated2DAssetResult
from app.schema.generation.request import Connection2D
from app.schema.generation.ws_event_generation_payload import Image2DAssetPayload
from app.schema.websocket.ws_event import Image2DGeneratedWSEvent
from app.service.generation.image_2d_feature_generation_service import (
    Image2DFeatureGenerationService,
)
from app.service.generation.image_2d_generation_service import Image2DGenerationService
from app.service.websocket.connection_manager import RoomConnectionManager, room_ws_manager

logger = get_logger(__name__)

GenerationCall = Callable[[Session], Awaitable[Generated2DAssetResult]]


class Image2DGenerationTaskService:
    """Own the background-session lifecycle and completion event publication."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        ws_manager: RoomConnectionManager = room_ws_manager,
    ) -> None:
        self.session_factory = session_factory
        self.ws_manager = ws_manager

    async def generate_from_graph(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        graph_snapshot_id: UUID,
        connections: list[Connection2D],
    ) -> None:
        await self._run(
            room_id=room_id,
            user_id=user_id,
            graph_snapshot_id=graph_snapshot_id,
            generation_call=lambda db: Image2DGenerationService(db=db).generate(
                room_id=room_id,
                user_id=user_id,
                graph_snapshot_id=graph_snapshot_id,
                connections=connections,
            ),
        )

    async def generate_from_features(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
    ) -> None:
        await self._run(
            room_id=room_id,
            user_id=user_id,
            graph_snapshot_id=None,
            generation_call=lambda db: Image2DFeatureGenerationService(db=db).generate(
                room_id=room_id,
                user_id=user_id,
            ),
        )

    async def _run(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        graph_snapshot_id: UUID | None,
        generation_call: GenerationCall,
    ) -> None:
        db = self.session_factory()

        logger.info(
            "[2d_generation_task_started] room_id=%s | user_id=%s | graph_snapshot_id=%s",
            room_id,
            user_id,
            graph_snapshot_id,
        )

        try:
            result = await generation_call(db)
            event = Image2DGeneratedWSEvent(
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

            await self.ws_manager.send_to_user(
                room_id=room_id,
                user_id=user_id,
                message=event.model_dump(mode="json"),
            )

            logger.info(
                "[2d_generation_task_completed] room_id=%s | graph_snapshot_id=%s | asset_id=%s",
                room_id,
                graph_snapshot_id,
                result.asset_id,
            )

        except Exception as error:
            db.rollback()
            logger.exception(
                "[2d_generation_task_failed] room_id=%s | graph_snapshot_id=%s | error=%s",
                room_id,
                graph_snapshot_id,
                str(error),
            )

        finally:
            db.close()
            logger.info(
                "[2d_generation_task_db_closed] room_id=%s | graph_snapshot_id=%s",
                room_id,
                graph_snapshot_id,
            )
