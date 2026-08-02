from uuid import UUID

from sqlalchemy.orm import Session

from app.model.feature import Feature
from app.repository.feature_repository import FeatureRepository
from app.repository.room_repository import RoomRepository
from app.schema.feature.request import (
    GenerateFeaturesRequest,
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
    ServerException,
)
from app.core.logger import get_logger
from app.service.feature.feature_extraction_service import FeatureExtractionService

logger = get_logger(__name__)


class FeatureService:
    def __init__(
        self,
        *,
        feature_repository: FeatureRepository | None = None,
        room_repository: RoomRepository | None = None,
        feature_extraction_service: FeatureExtractionService | None = None,
    ) -> None:
        self.feature_repository = feature_repository or FeatureRepository()
        self.room_repository = room_repository or RoomRepository()
        self.feature_extraction_service = (
            feature_extraction_service or FeatureExtractionService()
        )

    # =========================
    # 기능 생성
    # POST /api/features/generate
    # =========================
    async def generate_features(
        self,
        request: GenerateFeaturesRequest,
        db: Session,
    ) -> FeatureListResponse:
        logger.info(
            "[service_generate_features] start | room_id=%s | feature_length=%s",
            request.room_id,
            len(request.feature_text),
        )

        if not request.room_id or not any(
            character.isalnum() for character in request.feature_text
        ):
            logger.warning("[service_generate_features] invalid request")
            raise BadRequestException(code=ResponseCode.FEATURE400)

        room = self.room_repository.find_room_by_id(db, request.room_id)
        if room is None:
            logger.warning(
                "[service_generate_features] room not found | room_id=%s",
                request.room_id,
            )
            raise NotFoundException(code=ResponseCode.ROOM404)

        if not room.is_active:
            raise BadRequestException(
                code=ResponseCode.FEATURE400,
                message="비활성화된 회의실에서는 기능을 생성할 수 없습니다.",
            )

        extracted_feature_texts = await self.feature_extraction_service.extract(
            feature_text=request.feature_text,
        )
        features = [
            Feature(
                room_id=request.room_id,
                feature_text=feature_text,
            )
            for feature_text in extracted_feature_texts
        ]

        try:
            saved_features = self.feature_repository.save_features(
                db=db,
                features=features,
            )
            response = FeatureListResponse(
                room_id=request.room_id,
                features=[
                    FeatureInfo(
                        feature_id=feature.feature_id,
                        feature_text=feature.feature_text,
                    )
                    for feature in saved_features
                ],
            )
            db.commit()
        except Exception as error:
            db.rollback()
            logger.exception(
                "[service_generate_features] persistence failed | room_id=%s | feature_count=%s | error=%s",
                request.room_id,
                len(features),
                str(error),
            )
            raise ServerException(
                code=ResponseCode.FEATURE500,
                message="추출된 기능을 저장하지 못했습니다.",
            ) from error

        logger.info(
            "[service_generate_features] success | room_id=%s | feature_count=%s",
            request.room_id,
            len(response.features),
        )
        return response

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
