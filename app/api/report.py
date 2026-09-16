from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.response.code import ResponseCode
from app.core.response.response import success_response
from app.db.session import get_db
from app.service.report.meeting_report_service import MeetingReportService
from app.service.report.meeting_report_task_service import MeetingReportTaskService
from app.service.report.report_service import ReportService

router = APIRouter(tags=["Report"])

templates = Jinja2Templates(directory=Path(__file__).parents[1] / "templates")

# 리포트는 한국 사용자가 읽는다. 한국은 서머타임이 없어 고정 오프셋으로 충분하고,
# slim 이미지에 tzdata 가 없어도 동작한다.
KST = timezone(timedelta(hours=9))


def _format_kst(value: datetime | None, pattern: str) -> str:
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(KST).strftime(pattern)


def _format_duration(seconds: int | None) -> str:
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}시간 {minutes}분"
    return f"{minutes}분"


templates.env.filters["kst"] = lambda value: _format_kst(value, "%Y.%m.%d %H:%M")
templates.env.filters["kst_time"] = lambda value: _format_kst(value, "%H:%M:%S")
templates.env.filters["duration"] = _format_duration

# 로그인 없이 브라우저로 여는 페이지라, 추측 불가능한 UUID URL 자체가 접근 권한이다.
# 검색엔진 색인·Referer 로 주소가 새지 않게 막는다.
REPORT_PAGE_HEADERS = {
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def get_report_service() -> ReportService:
    return ReportService()


def get_meeting_report_service() -> MeetingReportService:
    return MeetingReportService()


meeting_report_task_service = MeetingReportTaskService()


def get_meeting_report_task_service() -> MeetingReportTaskService:
    return meeting_report_task_service


@router.get("/report/{room_id}")
def get_report(
    room_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    report_service: ReportService = Depends(get_report_service),
    task_service: MeetingReportTaskService = Depends(get_meeting_report_task_service),
):
    base_url = str(request.base_url)
    result = report_service.get_report(
        db=db,
        room_id=room_id,
        base_url=base_url,
    )
    background_tasks.add_task(
        task_service.run,
        report_id=result.report_id,
        room_id=room_id,
        user_id=None,
        base_url=base_url,
    )
    return success_response(
        code=ResponseCode.REPORT200,
        result=result.response,
    )


@router.get(
    "/reports/{report_id}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def get_meeting_report_page(
    report_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    meeting_report_service: MeetingReportService = Depends(get_meeting_report_service),
):
    page = meeting_report_service.find_report_page(
        db,
        report_id=report_id,
        base_url=str(request.base_url),
    )
    if page is None:
        return templates.TemplateResponse(
            request,
            "meeting_report_not_found.html",
            status_code=404,
            headers=REPORT_PAGE_HEADERS,
        )

    return templates.TemplateResponse(
        request,
        "meeting_report.html",
        context={"page": page},
        headers=REPORT_PAGE_HEADERS,
    )
