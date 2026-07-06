from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.repository.asset_repository import AssetRepository
from app.schema.generation.request import Connection2D
from app.schema.generation.generation_result import (
    Generated2DAssetResult,
    StoredObjectInfo,
)
from app.service.generation.gemini_image_client import GeminiImageClient
from app.service.generation.minio_asset_storage import MinioAssetStorage
from app.service.generation.prompt_context_builder import PromptContextBuilder
from app.service.generation.prompt_generation_service import PromptGenerationService

logger = get_logger(__name__)


class Image2DGenerationService:
    def __init__(
        self,
        *,
        db: Session,
        prompt_context_builder: PromptContextBuilder | None = None,
        prompt_generation_service: PromptGenerationService | None = None,
        gemini_image_client: GeminiImageClient | None = None,
        minio_asset_storage: MinioAssetStorage | None = None,
        asset_repository: AssetRepository | None = None,
    ) -> None:
        self.db = db
        self.prompt_context_builder = prompt_context_builder or PromptContextBuilder()
        self.prompt_generation_service = prompt_generation_service or PromptGenerationService()
        self.gemini_image_client = gemini_image_client or GeminiImageClient()
        self.minio_asset_storage = minio_asset_storage or MinioAssetStorage()
        self.asset_repository = asset_repository or AssetRepository()

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

        stored_object: StoredObjectInfo | None = None

        try:
            context = self.prompt_context_builder.build(
                db=self.db,
                room_id=room_id,
                connections=connections,
            )

            prompt_text = await self.prompt_generation_service.generate(
                context=context,
            )

            generated_image = await self.gemini_image_client.generate_image(
                prompt_text=prompt_text,
            )

            stored_object = self.minio_asset_storage.upload_generated_image(
                room_id=room_id,
                graph_snapshot_id=graph_snapshot_id,
                image_bytes=generated_image.image_bytes,
                mime_type=generated_image.mime_type,
            )

            asset = self.asset_repository.create_2d_asset(
                db=self.db,
                room_id=room_id,
                graph_snapshot_id=graph_snapshot_id,
                file_url=stored_object.public_url,
                prompt_text=prompt_text,
            )

            self.db.commit()

            logger.info(
                "[image_2d_generation_completed] room_id=%s | asset_id=%s",
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
                "[image_2d_generation_failed] room_id=%s | graph_snapshot_id=%s",
                room_id,
                graph_snapshot_id,
            )

            if stored_object is not None:
                try:
                    self.minio_asset_storage.delete_uploaded_image(
                        bucket_name=stored_object.bucket_name,
                        object_name=stored_object.object_name,
                    )
                except Exception as cleanup_error:
                    logger.exception(
                        "[image_2d_generation_cleanup_failed] room_id=%s | error=%s",
                        room_id,
                        str(cleanup_error),
                    )

            raise