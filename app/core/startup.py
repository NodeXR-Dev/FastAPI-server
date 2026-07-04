from app.core.config import settings
from app.core.logger import get_logger
from app.core.minio import MinioManager

logger = get_logger(__name__)


def bootstrap_infrastructure() -> None:
    logger.info("[bootstrap_infrastructure_started]")

    minio_manager = MinioManager()
    minio_manager.ensure_bucket_exists(
        bucket_name=settings.MINIO_BUCKET_2D_ASSETS,
        public_read=True,
    )

    logger.info("[bootstrap_infrastructure_completed]")