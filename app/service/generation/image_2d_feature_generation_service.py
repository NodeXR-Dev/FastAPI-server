from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.repository.asset_repository import AssetRepository
from app.schema.generation.generation_result import (
    Generated2DAssetResult,
    StoredObjectInfo,
)
from app.service.generation.feature_prompt_context_builder import FeaturePromptContextBuilder
from app.service.generation.feature_prompt_generation_service import FeaturePromptGenerationService
from app.service.generation.gemini_image_client import GeminiImageClient
from app.service.generation.minio_asset_storage import MinioAssetStorage

logger = get_logger(__name__)


class Image2DFeatureGenerationService:
    def __init__(
        self,
        *,
        db: Session,
        feature_prompt_context_builder: FeaturePromptContextBuilder | None = None,
        feature_prompt_generation_service: FeaturePromptGenerationService | None = None,
        gemini_image_client: GeminiImageClient | None = None,
        minio_asset_storage: MinioAssetStorage | None = None,
        asset_repository: AssetRepository | None = None,
    ) -> None:
        self.db = db
        self.feature_prompt_context_builder = (
            feature_prompt_context_builder or FeaturePromptContextBuilder()
        )
        self.feature_prompt_generation_service = (
            feature_prompt_generation_service or FeaturePromptGenerationService()
        )
        self.gemini_image_client = gemini_image_client or GeminiImageClient()
        self.minio_asset_storage = minio_asset_storage or MinioAssetStorage()
        self.asset_repository = asset_repository or AssetRepository()

    async def generate(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
    ) -> Generated2DAssetResult:
        logger.info(
            "[image_2d_feature_generation_started] room_id=%s | user_id=%s ",
            room_id,
            user_id,
        )

        stored_object: StoredObjectInfo | None = None

        try:
            context = self.feature_prompt_context_builder.build(
                db=self.db,
                room_id=room_id,
            )

            prompt_text = await self.feature_prompt_generation_service.generate(
                context=context,
            )

            generated_image = await self.gemini_image_client.generate_image(
                prompt_text=prompt_text,
            )

            stored_object = self.minio_asset_storage.upload_generated_image(
                room_id=room_id,
                graph_snapshot_id=None,
                image_bytes=generated_image.image_bytes,
                mime_type=generated_image.mime_type,
            )

            asset = self.asset_repository.create_2d_asset(
                db=self.db,
                room_id=room_id,
                graph_snapshot_id=None,
                file_url=stored_object.public_url,
                prompt_text=prompt_text,
            )

            self.db.commit()

            logger.info(
                "[image_2d_feature_generation_completed] room_id=%s | asset_id=%s",
                room_id,
                asset.asset_id,
            )

            return Generated2DAssetResult(
                asset_id=asset.asset_id,
                mime_type=generated_image.mime_type,
                width=generated_image.width,
                height=generated_image.height,
                img_url=stored_object.public_url,
            )

        except Exception:
            self.db.rollback()

            logger.exception(
                "[image_2d_feature_generation_failed] room_id=%s",
                room_id,
            )

            if stored_object is not None:
                try:
                    self.minio_asset_storage.delete_uploaded_image(
                        bucket_name=stored_object.bucket_name,
                        object_name=stored_object.object_name,
                    )
                except Exception as cleanup_error:
                    logger.exception(
                        "[image_2d_feature_generation_cleanup_failed] room_id=%s | error=%s",
                        room_id,
                        str(cleanup_error),
                    )

            raise