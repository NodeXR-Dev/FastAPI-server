from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.response.response import success_response
from app.core.response.code import ResponseCode
from app.db.session import get_db
from app.schema.room.request import CreateRoomRequest, EnterRoomRequest, ExitRoomRequest
from app.service.room.room_service import RoomService

router = APIRouter(
    prefix="/rooms",
    tags=["Room"],
)

room_service = RoomService()


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
        result=result,
    )


@router.get("/list")
def get_room_list(
    db: Session = Depends(get_db),
):
    result = room_service.get_room_list(db=db)

    return success_response(
        code=ResponseCode.ROOM201,
        result=result,
    )


@router.get("/{room_id}/info")
def get_room_info(
    room_id: UUID,
    db: Session = Depends(get_db),
):
    result = room_service.get_room_info(
        db=db,
        room_id=room_id,
    )

    return success_response(
        code=ResponseCode.ROOM202,
        result=result,
    )


@router.post("/enter")
def enter_room(
    request: EnterRoomRequest,
    db: Session = Depends(get_db),
):
    result, is_reenter = room_service.enter_room(
        db=db,
        request=request,
    )

    if is_reenter:
        return success_response(
            code=ResponseCode.ROOM204,
            result=result,
        )

    return success_response(
        code=ResponseCode.ROOM203,
        result=result,
    )

@router.patch("/exit")
def exit_room(
    request: ExitRoomRequest,
    db: Session = Depends(get_db),
):
    result = room_service.exit_room(
        request=request,
        db=db
    )
    
    return success_response(
        code=ResponseCode.ROOM205,
        result=result
    )