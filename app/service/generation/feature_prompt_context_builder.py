from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.repository.feature_repository import FeatureRepository
from app.repository.room_repository import RoomRepository
from app.schema.generation.generation_result import FeaturePromptContext

logger = get_logger(__name__)


class FeaturePromptContextBuilder:
    def __init__(
        self,
        *,
        room_repository: RoomRepository | None = None,
        feature_repository: FeatureRepository | None = None,
    ) -> None:
        self.room_repository = room_repository or RoomRepository()
        self.feature_repository = feature_repository or FeatureRepository()

    def build(
        self,
        *,
        db: Session,
        room_id: UUID,
    ) -> FeaturePromptContext:
        logger.info(
            "[feature_prompt_context_build_started] room_id=%s",
            room_id,
        )

        topic = self.room_repository.find_room_topic(
            db=db,
            room_id=room_id,
        )

        features = self.feature_repository.find_feature_texts(
            db=db,
            room_id=room_id,
        )

        if not features:
            logger.warning(
                "[feature_prompt_context_empty_features] room_id=%s",
                room_id,
            )

        context = FeaturePromptContext(
            room_id=room_id,
            topic=topic,
            features=features,
        )

        logger.info(
            "[feature_prompt_context_build_completed] room_id=%s | topic_length=%s | feature_count=%s",
            room_id,
            len(topic),
            len(features),
        )

        return context