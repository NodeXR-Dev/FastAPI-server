# app/api/routes/room.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.response.response import success_response
from app.core.response.code import ResponseCode
from app.db.session import get_db
from app.schema.room.request import CreateRoomRequest, EnterRoomRequest
from app.service.room.room_service import RoomService

router = APIRouter(
    prefix="/rooms",
    tags=["Room"],
)

room_service = RoomService()


# =========================
# 회의실 생성
# POST /api/rooms/generate
# =========================

@router.post("/generate")
def create_room(
    request: CreateRoomRequest,
    db: Session = Depends(get_db),
):
    result = room_service.create_room(
        db=db,
        request=request,
    )

    return success_response(
        code=ResponseCode.ROOM200,
        message="회의실 생성 성공",
        result=result,
    )


# =========================
# 회의실 목록 조회
# GET /api/rooms/list
# =========================

@router.get("/list")
def get_room_list(
    db: Session = Depends(get_db),
):
    result = room_service.get_room_list(db=db)

    return success_response(
        code=ResponseCode.ROOM201,
        message="회의실 목록 조회 성공",
        result=result,
    )


# =========================
# 회의실 상세 정보 조회
# GET /api/rooms/{room_id}/info
# =========================

@router.get("/{room_id}/info")
def get_room_info(
    room_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        result = room_service.get_room_info(
            db=db,
            room_id=room_id,
        )

    except ValueError as e:
        if str(e) == "ROOM_NOT_FOUND":
            raise HTTPException(
                status_code=404,
                detail={
                    "code": ResponseCode.ROOM404,
                    "message": "회의실을 찾을 수 없습니다.",
                },
            )

        raise HTTPException(
            status_code=400,
            detail={
                "code": ResponseCode.ROOM400,
                "message": "회의실 상세 정보 조회 실패",
            },
        )

    return success_response(
        code=ResponseCode.ROOM202,
        message="회의실 상세 정보 조회 성공",
        result=result,
    )


# =========================
# 회의실 입장
# POST /api/rooms/enter
# =========================

@router.post("/enter")
def enter_room(
    request: EnterRoomRequest,
    db: Session = Depends(get_db),
):
    try:
        result, is_reenter = room_service.enter_room(
            db=db,
            request=request,
        )

    except ValueError as e:
        if str(e) == "ROOM_NOT_FOUND":
            raise HTTPException(
                status_code=404,
                detail={
                    "code": ResponseCode.ROOM404,
                    "message": "회의실을 찾을 수 없습니다.",
                },
            )

        raise HTTPException(
            status_code=400,
            detail={
                "code": ResponseCode.ROOM400,
                "message": "회의실 입장 실패",
            },
        )

    if is_reenter:
        return success_response(
            code=ResponseCode.ROOM204,
            message="회의실 재입장 성공",
            result=result,
        )

    return success_response(
        code=ResponseCode.ROOM203,
        message="회의실 최초 입장 성공",
        result=result,
    )