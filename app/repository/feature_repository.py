from uuid import UUID

from sqlalchemy.orm import Session

from app.model.graph import Feature
from app.model.room import Room


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