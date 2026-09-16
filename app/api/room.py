from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.response.response import success_response
from app.core.response.code import ResponseCode
from app.db.session import get_db
from app.schema.room.request import (
    CreateRoomRequest,
    EndMeetingRequest,
    EnterRoomRequest,
    ExitRoomRequest,
)
from app.service.report.meeting_report_task_service import MeetingReportTaskService
from app.service.report.report_service import ReportService
from app.service.room.room_service import RoomService

router = APIRouter(
    prefix="/rooms",
    tags=["Room"],
)

room_service = RoomService()
report_service = ReportService()
meeting_report_task_service = MeetingReportTaskService()


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


@router.post(
    "/{room_id}/end",
    status_code=status.HTTP_202_ACCEPTED,
)
def end_meeting(
    room_id: UUID,
    request: EndMeetingRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """회의를 끝내고 리포트 생성을 요청한다.

    응답 body 는 GET /report/{room_id} 와 같다. 생성이 끝나면 요청자에게
    REPORT_GENERATED 를 보낸다. 같은 방에 여러 번 요청해도 리포트는 하나만 만든다.
    """
    base_url = str(http_request.base_url)
    result = report_service.get_report(
        db=db,
        room_id=room_id,
        base_url=base_url,
        user_id=request.user_id,
    )

    background_tasks.add_task(
        meeting_report_task_service.run,
        report_id=result.report_id,
        room_id=room_id,
        user_id=request.user_id,
        base_url=base_url,
    )

    return success_response(
        code=ResponseCode.REPORT200,
        result=result.response,
    )
