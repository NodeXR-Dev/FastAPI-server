import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

from app.agent.schema.realtime_agent_schema import AgentResponse, GenerationRequest
from app.core.logger import get_logger
from app.db.session import SessionLocal
from app.schema.generation.request import Generate3DRequest
from app.service.generation.image_2d_generation_task_service import (
    Image2DGenerationTaskService,
)
from app.service.generation.model_3d_generation_service import Model3DGenerationService

logger = get_logger(__name__)


class AssetGenerationAdapter:
    def __init__(
        self,
        *,
        image_2d_task_service: Image2DGenerationTaskService | None = None,
        model_3d_service: Model3DGenerationService | None = None,
    ) -> None:
        self.image_2d_task_service = (
            image_2d_task_service or Image2DGenerationTaskService()
        )
        self.model_3d_service = model_3d_service or Model3DGenerationService()
        self._tasks: set[asyncio.Task] = set()

    async def enqueue(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        request: GenerationRequest,
    ) -> AgentResponse:
        if request.asset_type == "IMAGE_2D":
            self._spawn(
                self.image_2d_task_service.generate_from_features(
                    room_id=room_id,
                    user_id=user_id,
                )
            )
            return AgentResponse(
                response_type="ASSET_GENERATION",
                message="2D 이미지 생성 요청을 접수했습니다.",
            )

        if request.asset_type == "MODEL_3D":
            if request.source_asset_id is None:
                return AgentResponse(
                    response_type="ASSET_GENERATION",
                    message="3D 생성에는 원본 2D Asset ID가 필요합니다.",
                )
            await asyncio.to_thread(
                self._validate_3d_request,
                room_id=room_id,
                source_asset_id=request.source_asset_id,
            )
            self._spawn(
                self.model_3d_service.run(
                    room_id=room_id,
                    source_asset_id=request.source_asset_id,
                )
            )
            return AgentResponse(
                response_type="ASSET_GENERATION",
                message="3D 모델 생성 요청을 접수했습니다.",
            )

        return AgentResponse(
            response_type="ASSET_GENERATION",
            message=(
                "Reference 생성에는 이미지 파일과 대상 노드 정보가 필요합니다. "
                "기존 Reference 업로드 API를 사용해 주세요."
            ),
        )

    def _validate_3d_request(self, *, room_id: UUID, source_asset_id: UUID) -> None:
        db = SessionLocal()
        try:
            self.model_3d_service.validate_request(
                db=db,
                request=Generate3DRequest(
                    room_id=room_id,
                    asset_id=source_asset_id,
                ),
            )
        finally:
            db.close()

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.exception(
                "[agent_asset_task_failed] error=%s",
                str(error),
                exc_info=error,
            )
