from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.schema.generation.generation_result import Generated2DAssetResult
from app.schema.generation.request import Connection2D
from app.service.generation.image_2d_asset_generation_service import (
    Image2DAssetGenerationService,
)
from app.service.generation.openai_prompt_client import OpenAIPromptClient
from app.service.generation.prompt_context_builder import PromptContextBuilder

logger = get_logger(__name__)


class Image2DGenerationService:
    def __init__(
        self,
        *,
        db: Session,
        prompt_context_builder: PromptContextBuilder | None = None,
        openai_prompt_client: OpenAIPromptClient | None = None,
        asset_generation_service: Image2DAssetGenerationService | None = None,
    ) -> None:
        self.db = db
        self.prompt_context_builder = prompt_context_builder or PromptContextBuilder()
        self.openai_prompt_client = openai_prompt_client or OpenAIPromptClient()
        self.asset_generation_service = (
            asset_generation_service or Image2DAssetGenerationService(db=db)
        )

    async def generate(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        graph_snapshot_id: UUID,
        connections: list[Connection2D],
    ) -> Generated2DAssetResult:
        logger.info(
            "[image_2d_generation_started] room_id=%s | user_id=%s | graph_snapshot_id=%s | connection_count=%s",
            room_id,
            user_id,
            graph_snapshot_id,
            len(connections),
        )

        try:
            context = self.prompt_context_builder.build(
                db=self.db,
                room_id=room_id,
                connections=connections,
            )

            prompt_text = await self.openai_prompt_client.generate_image_prompt(
                context_text=context.to_text(),
            )

            result = await self.asset_generation_service.generate(
                room_id=room_id,
                user_id=user_id,
                graph_snapshot_id=graph_snapshot_id,
                prompt_text=prompt_text,
            )

            logger.info(
                "[image_2d_generation_completed] room_id=%s | asset_id=%s",
                room_id,
                result.asset_id,
            )

            return result

        except Exception:
            logger.exception(
                "[image_2d_generation_failed] room_id=%s | graph_snapshot_id=%s",
                room_id,
                graph_snapshot_id,
            )
            raise
