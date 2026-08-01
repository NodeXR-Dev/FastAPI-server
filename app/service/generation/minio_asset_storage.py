from urllib.parse import unquote, urlparse
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

    def upload_reference_image(
        self,
        *,
        room_id: UUID,
        image_bytes: bytes,
        mime_type: str,
    ) -> StoredObjectInfo:
        logger.info(
            "[upload_reference_image_started] room_id=%s | mime_type=%s",
            room_id,
            mime_type,
        )

        extension = self._resolve_extension(mime_type=mime_type)
        object_name = f"references/{room_id}/{uuid4()}.{extension}"

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
            "[upload_reference_image_completed] room_id=%s | object_name=%s",
            room_id,
            object_name,
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

    def delete_reference_image(self, *, image_url: str) -> bool:
        object_name = self._resolve_managed_object_name(image_url=image_url)

        if object_name is None or not object_name.startswith("references/"):
            logger.warning(
                "[delete_reference_image_skipped] unmanaged_image_url=%s",
                image_url,
            )
            return False

        self.delete_uploaded_image(
            bucket_name=settings.MINIO_BUCKET_2D_ASSETS,
            object_name=object_name,
        )
        return True

    def validate_generated_image_url(self, *, image_url: str) -> bool:
        object_name = self._resolve_managed_object_name(image_url=image_url)
        return object_name is not None and object_name.startswith("2d/")

    def download_generated_image(self, *, image_url: str) -> bytes:
        object_name = self._resolve_managed_object_name(image_url=image_url)

        if object_name is None or not object_name.startswith("2d/"):
            raise ValueError("관리되는 2D Asset URL이 아닙니다.")

        return self.minio_manager.download_bytes(
            bucket_name=settings.MINIO_BUCKET_2D_ASSETS,
            object_name=object_name,
        )

    @staticmethod
    def _resolve_managed_object_name(*, image_url: str) -> str | None:
        base_url = settings.MINIO_PUBLIC_BASE_URL.rstrip("/")
        bucket_name = settings.MINIO_BUCKET_2D_ASSETS
        expected_prefix = f"{urlparse(base_url).path.rstrip('/')}/{bucket_name}/"
        parsed_url = urlparse(image_url)
        parsed_base_url = urlparse(base_url)

        if (
            parsed_url.scheme != parsed_base_url.scheme
            or parsed_url.netloc != parsed_base_url.netloc
            or not parsed_url.path.startswith(expected_prefix)
        ):
            return None

        object_name = unquote(parsed_url.path[len(expected_prefix):])

        if (
            not object_name
            or object_name.startswith("/")
            or ".." in object_name.split("/")
        ):
            return None

        return object_name

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
