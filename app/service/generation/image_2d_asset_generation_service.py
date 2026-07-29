from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.model.enum import GraphEventType
from app.repository.asset_repository import AssetRepository
from app.repository.graph_repository import GraphRepository
from app.schema.generation.generation_result import (
    Generated2DAssetResult,
    StoredObjectInfo,
)
from app.service.generation.gemini_image_client import GeminiImageClient
from app.service.generation.minio_asset_storage import MinioAssetStorage

logger = get_logger(__name__)


class Image2DAssetGenerationService:
    """Generate, store, and persist a 2D image from an already-built prompt."""

    def __init__(
        self,
        *,
        db: Session,
        gemini_image_client: GeminiImageClient | None = None,
        minio_asset_storage: MinioAssetStorage | None = None,
        asset_repository: AssetRepository | None = None,
        graph_repository: GraphRepository | None = None,
    ) -> None:
        self.db = db
        self.gemini_image_client = gemini_image_client or GeminiImageClient()
        self.minio_asset_storage = minio_asset_storage or MinioAssetStorage()
        self.asset_repository = asset_repository or AssetRepository()
        self.graph_repository = graph_repository or GraphRepository()

    async def generate(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        graph_snapshot_id: UUID | None,
        prompt_text: str,
    ) -> Generated2DAssetResult:
        stored_object: StoredObjectInfo | None = None

        try:
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

            core_2d_image = {
                "asset_id": str(asset.asset_id),
                "image_url": stored_object.public_url,
                "mime_type": generated_image.mime_type,
                "width": generated_image.width,
                "height": generated_image.height,
            }
            updated_graph_snapshot = (
                self.graph_repository.create_graph_snapshot_from_current_graph(
                    db=self.db,
                    room_id=room_id,
                    core_2d_image=core_2d_image,
                )
            )

            self.graph_repository.create_graph_event(
                db=self.db,
                room_id=room_id,
                user_id=user_id,
                event_type=GraphEventType.GENERATE_2D,
                graph_snapshot_id=updated_graph_snapshot.graph_snapshot_id,
                payload={
                    "interaction_type": GraphEventType.GENERATE_2D.value,
                    "asset_id": str(asset.asset_id),
                    "image_url": stored_object.public_url,
                    "mime_type": generated_image.mime_type,
                    "width": generated_image.width,
                    "height": generated_image.height,
                    "source_graph_snapshot_id": (
                        str(graph_snapshot_id) if graph_snapshot_id else None
                    ),
                    "graph_snapshot_id": str(
                        updated_graph_snapshot.graph_snapshot_id,
                    ),
                },
            )

            self.db.commit()

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
                "[image_2d_asset_generation_failed] room_id=%s | graph_snapshot_id=%s",
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
                        "[image_2d_asset_cleanup_failed] room_id=%s | object_name=%s | error=%s",
                        room_id,
                        stored_object.object_name,
                        str(cleanup_error),
                    )

            raise
