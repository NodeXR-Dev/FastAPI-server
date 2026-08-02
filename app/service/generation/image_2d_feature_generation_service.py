from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.schema.generation.generation_result import Generated2DAssetResult
from app.service.generation.feature_prompt_context_builder import (
    FeaturePromptContextBuilder,
)
from app.service.generation.image_2d_asset_generation_service import (
    Image2DAssetGenerationService,
)
from app.service.generation.openai_prompt_client import OpenAIPromptClient

logger = get_logger(__name__)


class Image2DFeatureGenerationService:
    def __init__(
        self,
        *,
        db: Session,
        feature_prompt_context_builder: FeaturePromptContextBuilder | None = None,
        openai_prompt_client: OpenAIPromptClient | None = None,
        asset_generation_service: Image2DAssetGenerationService | None = None,
    ) -> None:
        self.db = db
        self.feature_prompt_context_builder = (
            feature_prompt_context_builder or FeaturePromptContextBuilder()
        )
        self.openai_prompt_client = openai_prompt_client or OpenAIPromptClient()
        self.asset_generation_service = (
            asset_generation_service or Image2DAssetGenerationService(db=db)
        )

    async def generate(
        self,
        *,
        room_id: UUID,
        user_id: UUID | None,
    ) -> Generated2DAssetResult:
        logger.info(
            "[image_2d_feature_generation_started] room_id=%s | user_id=%s ",
            room_id,
            user_id,
        )

        try:
            context = self.feature_prompt_context_builder.build(
                db=self.db,
                room_id=room_id,
            )

            prompt_text = await self.openai_prompt_client.generate_feature_image_prompt(
                context_text=context.to_text(),
            )

            result = await self.asset_generation_service.generate(
                room_id=room_id,
                user_id=user_id,
                graph_snapshot_id=None,
                prompt_text=prompt_text,
            )

            logger.info(
                "[image_2d_feature_generation_completed] room_id=%s | asset_id=%s",
                room_id,
                result.asset_id,
            )

            return result

        except Exception:
            logger.exception(
                "[image_2d_feature_generation_failed] room_id=%s",
                room_id,
            )
            raise
