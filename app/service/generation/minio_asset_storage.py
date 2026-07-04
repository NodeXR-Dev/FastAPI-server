from uuid import UUID, uuid4

from app.core.config import settings
from app.core.logger import get_logger
from app.core.minio import MinioManager
from app.schema.generation.generation_result import StoredObjectInfo

logger = get_logger(__name__)


class MinioAssetStorage:
    def __init__(
        self,
        *,
        minio_manager: MinioManager | None = None,
    ) -> None:
        self.minio_manager = minio_manager or MinioManager()

    def upload_generated_image(
        self,
        *,
        room_id: UUID,
        graph_snapshot_id: UUID | None=None,
        image_bytes: bytes,
        mime_type: str,
    ) -> StoredObjectInfo:
        logger.info(
            "[upload_generated_image_started] room_id=%s | graph_snapshot_id=%s | mime_type=%s",
            room_id,
            graph_snapshot_id,
            mime_type,
        )

        extension = self._resolve_extension(
            mime_type=mime_type,
        )

        object_name = f"2d/{room_id}/{graph_snapshot_id}/{uuid4()}.{extension}"

        self.minio_manager.upload_bytes(
            bucket_name=settings.MINIO_BUCKET_2D_ASSETS,
            object_name=object_name,
            data=image_bytes,
            content_type=mime_type,
        )

        public_url = self.minio_manager.build_public_url(
            bucket_name=settings.MINIO_BUCKET_2D_ASSETS,
            object_name=object_name,
        )

        logger.info(
            "[upload_generated_image_completed] object_name=%s | public_url=%s",
            object_name,
            public_url,
        )

        return StoredObjectInfo(
            bucket_name=settings.MINIO_BUCKET_2D_ASSETS,
            object_name=object_name,
            public_url=public_url,
        )

    def delete_uploaded_image(
        self,
        *,
        bucket_name: str,
        object_name: str,
    ) -> None:
        logger.info(
            "[delete_uploaded_image_started] bucket_name=%s | object_name=%s",
            bucket_name,
            object_name,
        )

        self.minio_manager.remove_object(
            bucket_name=bucket_name,
            object_name=object_name,
        )

        logger.info(
            "[delete_uploaded_image_completed] bucket_name=%s | object_name=%s",
            bucket_name,
            object_name,
        )

    @staticmethod
    def _resolve_extension(
        *,
        mime_type: str,
    ) -> str:
        if mime_type == "image/jpeg":
            return "jpg"

        if mime_type == "image/webp":
            return "webp"

        return "png"