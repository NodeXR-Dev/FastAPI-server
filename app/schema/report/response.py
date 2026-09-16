from uuid import UUID

from pydantic import BaseModel, Field


class ParticipantRatioResponse(BaseModel):
    user_id: UUID
    nickname: str
    # 발화 횟수 기준 비율(%).
    ratio: float = Field(ge=0.0, le=100.0)


class ReportResponse(BaseModel):
    topic: str
    participants: list[str]
    participants_ratio: list[ParticipantRatioResponse]
    final_2D_image: str | None
    # 회의 리포트 HTML 페이지 주소. 생성 중이어도 주소는 확정이며 페이지가 진행 상태를 보여준다.
    url: str


class MeetingReportLinkResponse(BaseModel):
    """서비스 내부에서 쓰는 리포트 식별 정보. 클라이언트 응답은 ReportResponse 다."""

    report_id: UUID
    room_id: UUID
    report_version: int
    status: str
    report_url: str
