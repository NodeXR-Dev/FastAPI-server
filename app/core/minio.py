import json
from io import BytesIO

from minio import Minio

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class MinioManager:
    def __init__(self) -> None:
        self.client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )

    def ensure_bucket_exists(
        self,
        *,
        bucket_name: str,
        public_read: bool = False,
    ) -> None:
        logger.info(
            "[minio_ensure_bucket_started] bucket_name=%s | public_read=%s",
            bucket_name,
            public_read,
        )

        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name)
            logger.info(
                "[minio_bucket_created] bucket_name=%s",
                bucket_name,
            )
        else:
            logger.info(
                "[minio_bucket_already_exists] bucket_name=%s",
                bucket_name,
            )

        if public_read:
            self._set_public_read_policy(bucket_name=bucket_name)

        logger.info(
            "[minio_ensure_bucket_completed] bucket_name=%s",
            bucket_name,
        )

    def _set_public_read_policy(
        self,
        *,
        bucket_name: str,
    ) -> None:
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetBucketLocation"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}"],
                },
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                },
            ],
        }

        self.client.set_bucket_policy(
            bucket_name,
            json.dumps(policy),
        )

        logger.info(
            "[minio_public_policy_set] bucket_name=%s",
            bucket_name,
        )

    def upload_bytes(
        self,
        *,
        bucket_name: str,
        object_name: str,
        data: bytes,
        content_type: str,
    ) -> None:
        logger.info(
            "[minio_upload_started] bucket_name=%s | object_name=%s | content_type=%s | size=%s",
            bucket_name,
            object_name,
            content_type,
            len(data),
        )

        self.client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

        logger.info(
            "[minio_upload_completed] bucket_name=%s | object_name=%s",
            bucket_name,
            object_name,
        )

    def remove_object(
        self,
        *,
        bucket_name: str,
        object_name: str,
    ) -> None:
        self.client.remove_object(
            bucket_name,
            object_name,
        )

        logger.info(
            "[minio_object_removed] bucket_name=%s | object_name=%s",
            bucket_name,
            object_name,
        )

    def download_bytes(
        self,
        *,
        bucket_name: str,
        object_name: str,
    ) -> bytes:
        logger.info(
            "[minio_download_started] bucket_name=%s | object_name=%s",
            bucket_name,
            object_name,
        )
        response = self.client.get_object(bucket_name, object_name)

        try:
            data = response.read()
        finally:
            response.close()
            response.release_conn()

        logger.info(
            "[minio_download_completed] bucket_name=%s | object_name=%s | size=%s",
            bucket_name,
            object_name,
            len(data),
        )
        return data

    def build_public_url(
        self,
        *,
        bucket_name: str,
        object_name: str,
    ) -> str:
        return f"{settings.MINIO_PUBLIC_BASE_URL.rstrip('/')}/{bucket_name}/{object_name}"
