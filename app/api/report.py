from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.response.code import ResponseCode
from app.core.response.response import success_response
from app.db.session import get_db
from app.service.report.report_service import ReportService

router = APIRouter(tags=["Report"])


def get_report_service() -> ReportService:
    return ReportService()


@router.get("/report/{room_id}")
def get_report(
    room_id: UUID,
    db: Session = Depends(get_db),
    report_service: ReportService = Depends(get_report_service),
):
    result = report_service.get_report(
        db=db,
        room_id=room_id,
    )
    return success_response(
        code=ResponseCode.REPORT200,
        result=result,
    )
