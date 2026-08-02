from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.core.response.response import success_response
from app.db.session import get_db
from app.core.response.code import ResponseCode
from app.schema.feature.request import (
    GenerateFeaturesRequest,
    ModifyFeatureRequest,
    DeleteFeatureRequest,
)
from app.schema.feature.response import (
    FeatureResponse,
    FeatureListResponse,
)
from app.service.feature.feature_service import FeatureService
from app.service.generation.image_2d_generation_task_service import (
    Image2DGenerationTaskService,
)

router = APIRouter(
    prefix="/features",
    tags=["Feature"],
)

feature_service = FeatureService()
image_2d_generation_task_service = Image2DGenerationTaskService()


# =========================
# 기능 생성
# POST /api/features/generate
# =========================
@router.post("/generate")
async def generate_features(
    request: GenerateFeaturesRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    result: FeatureListResponse = await feature_service.generate_features(
        request=request,
        db=db,
    )

    background_tasks.add_task(
        image_2d_generation_task_service.generate_from_features,
        room_id=request.room_id,
        user_id=request.user_id,
        job_id=request.job_id,
    )

    return success_response(
        code=ResponseCode.FEATURE200,
        message="기능 목록 생성 및 초기 2D 스케치 요청이 접수되었습니다.",
        result={
            **result.model_dump(mode="json"),
            "job_id": str(request.job_id),
        },
    )


# =========================
# 기능 목록 조회
# GET /api/features/{room_id}
# =========================
@router.get("/{room_id}")
def get_feature_list(
    room_id: UUID,
    db: Session = Depends(get_db),
):
    result: FeatureListResponse = feature_service.get_feature_list(
        room_id=room_id,
        db=db,
    )

    return success_response(
        code=ResponseCode.FEATURE203,
        result=result,
    )


# =========================
# 기능 수정
# PATCH /api/features/modify
# =========================
@router.patch("/modify")
def modify_feature(
    request: ModifyFeatureRequest,
    db: Session = Depends(get_db),
):
    result: FeatureResponse = feature_service.modify_feature(
        request=request,
        db=db,
    )

    return success_response(
        code=ResponseCode.FEATURE201,
        result=result,
    )


# =========================
# 기능 삭제
# DELETE /api/features/delete
# =========================
@router.delete("/delete")
def delete_feature(
    request: DeleteFeatureRequest,
    db: Session = Depends(get_db),
):
    feature_service.delete_feature(
        request=request,
        db=db,
    )

    return success_response(
        code=ResponseCode.FEATURE202,
        result={},
    )
