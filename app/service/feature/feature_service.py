from uuid import UUID

from sqlalchemy.orm import Session

from app.model.graph import Feature
from app.repository.feature_repository import FeatureRepository
from app.repository.room_repository import RoomRepository
from app.schema.feature.request import (
    CreateFeatureRequest,
    ModifyFeatureRequest,
    DeleteFeatureRequest,
)
from app.schema.feature.response import (
    FeatureInfo,
    FeatureResponse,
    FeatureListResponse,
)
from app.core.response.code import ResponseCode
from app.core.response.exceptions import (
    BadRequestException,
    NotFoundException,
)
from app.core.logger import get_logger

logger = get_logger(__name__)


class FeatureService:
    def __init__(self):
        self.feature_repository = FeatureRepository()
        self.room_repository = RoomRepository()

    # =========================
    # 기능 생성
    # POST /api/features/generate
    # =========================
    def create_feature(
        self,
        request: CreateFeatureRequest,
        db: Session,
    ) -> FeatureResponse:
        logger.info(
            "[service_create_feature] start | room_id=%s | feature_length=%s",
            request.room_id,
            len(request.feature_text),
        )

        if not request.room_id or not request.feature_text:
            logger.warning("[service_create_feature] invalid request")
            raise BadRequestException(code=ResponseCode.FEATURE400)

        if not self.room_repository.find_room_by_id(db, request.room_id):
            logger.warning(
                "[service_create_feature] room not found | room_id=%s",
                request.room_id,
            )
            raise NotFoundException(code=ResponseCode.ROOM404)

        feature = Feature(
            room_id=request.room_id,
            feature_text=request.feature_text,
        )

        feature = self.feature_repository.save_feature(db, feature)

        db.commit()
        db.refresh(feature)

        logger.info(
            "[service_create_feature] success | room_id=%s | feature_id=%s",
            feature.room_id,
            feature.feature_id,
        )

        return FeatureResponse(
            room_id=feature.room_id,
            feature_id=feature.feature_id,
            feature_text=feature.feature_text,
        )

    # =========================
    # 기능 목록 조회
    # GET /api/features/{room_id}
    # =========================
    def get_feature_list(
        self,
        room_id: UUID,
        db: Session,
    ) -> FeatureListResponse:
        logger.info(
            "[service_get_feature_list] start | room_id=%s",
            room_id,
        )

        if not room_id:
            logger.warning("[service_get_feature_list] invalid request")
            raise BadRequestException(code=ResponseCode.FEATURE400)

        if not self.room_repository.find_room_by_id(db, room_id):
            logger.warning(
                "[service_get_feature_list] room not found | room_id=%s",
                room_id,
            )
            raise NotFoundException(code=ResponseCode.ROOM404)

        feature_items = self.feature_repository.find_features(db, room_id)

        features: list[FeatureInfo] = [
            FeatureInfo(
                feature_id=feature.feature_id,
                feature_text=feature.feature_text,
            )
            for feature in feature_items
        ]

        logger.info(
            "[service_get_feature_list] success | room_id=%s | feature_count=%s",
            room_id,
            len(features),
        )

        return FeatureListResponse(
            room_id=room_id,
            features=features,
        )

    # =========================
    # 기능 수정
    # PATCH /api/features/modify
    # =========================
    def modify_feature(
        self,
        request: ModifyFeatureRequest,
        db: Session,
    ) -> FeatureResponse:
        logger.info(
            "[service_modify_feature] start | room_id=%s | feature_id=%s",
            request.room_id,
            request.feature_id,
        )

        if not request.room_id or not request.feature_id or not request.feature_text:
            logger.warning("[service_modify_feature] invalid request")
            raise BadRequestException(code=ResponseCode.FEATURE400)

        feature = self.feature_repository.find_feature_by_id(
            db=db,
            room_id=request.room_id,
            feature_id=request.feature_id,
        )

        if feature is None:
            logger.warning(
                "[service_modify_feature] feature not found | room_id=%s | feature_id=%s",
                request.room_id,
                request.feature_id,
            )
            raise NotFoundException(code=ResponseCode.FEATURE404)

        feature.feature_text = request.feature_text

        db.commit()
        db.refresh(feature)

        logger.info(
            "[service_modify_feature] success | room_id=%s | feature_id=%s",
            feature.room_id,
            feature.feature_id,
        )

        return FeatureResponse(
            room_id=feature.room_id,
            feature_id=feature.feature_id,
            feature_text=feature.feature_text,
        )

    # =========================
    # 기능 삭제
    # DELETE /api/features/delete
    # =========================
    def delete_feature(
        self,
        request: DeleteFeatureRequest,
        db: Session,
    ) -> bool:
        logger.info(
            "[service_delete_feature] start | room_id=%s | feature_id=%s",
            request.room_id,
            request.feature_id,
        )

        if not request.room_id or not request.feature_id:
            logger.warning("[service_delete_feature] invalid request")
            raise BadRequestException(code=ResponseCode.FEATURE400)

        feature = self.feature_repository.find_feature_by_id(
            db=db,
            room_id=request.room_id,
            feature_id=request.feature_id,
        )

        if feature is None:
            logger.warning(
                "[service_delete_feature] feature not found | room_id=%s | feature_id=%s",
                request.room_id,
                request.feature_id,
            )
            raise NotFoundException(code=ResponseCode.FEATURE404)

        self.feature_repository.delete_feature(db, feature)

        db.commit()

        logger.info(
            "[service_delete_feature] success | room_id=%s | feature_id=%s",
            request.room_id,
            request.feature_id,
        )

        return True