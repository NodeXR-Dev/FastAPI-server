from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.model.feature import Feature
from app.model.room import Room

logger = get_logger(__name__)

class FeatureRepository:
    def save_feature(
        self,
        db: Session,
        feature: Feature,
    ) -> Feature:
        db.add(feature)
        db.flush()
        return feature

    def find_features(
        self,
        db: Session,
        room_id: UUID,
    ) -> list[Feature]:
        return db.query(Feature).filter(
            Feature.room_id == room_id
        ).order_by(
            Feature.feature_id.asc()
        ).all()

    def find_feature_by_id(
        self,
        db: Session,
        room_id: UUID,
        feature_id: UUID,
    ) -> Feature | None:
        return db.query(Feature).filter(
            Feature.room_id == room_id,
            Feature.feature_id == feature_id,
        ).first()

    def delete_feature(
        self,
        db: Session,
        feature: Feature,
    ) -> None:
        db.delete(feature)
        db.flush()
    
    def find_feature_texts(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> list[str]:
        logger.info(
            "[find_feature_texts_started] room_id=%s",
            room_id,
        )

        features = self.find_features(
            db=db,
            room_id=room_id,
        )

        feature_texts = [
            feature.feature_text
            for feature in features
            if feature.feature_text
        ]

        logger.info(
            "[find_feature_texts_completed] room_id=%s | feature_count=%s",
            room_id,
            len(feature_texts),
        )

        return feature_texts