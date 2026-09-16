from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.exceptions import NotFoundException
from app.repository.asset_repository import AssetRepository
from app.repository.report_repository import ReportRepository
from app.repository.room_repository import RoomRepository
from app.schema.report.response import ParticipantRatioResponse, ReportResponse
from app.service.report.meeting_report_service import MeetingReportService

logger = get_logger(__name__)


@dataclass(frozen=True)
class ReportResult:
    response: ReportResponse
    # 라우터가 BackgroundTasks 에 생성 작업을 걸 때 쓴다. 응답 body 에는 싣지 않는다.
    report_id: UUID


class ReportService:
    def __init__(
        self,
        *,
        room_repository: RoomRepository | None = None,
        report_repository: ReportRepository | None = None,
        asset_repository: AssetRepository | None = None,
        meeting_report_service: MeetingReportService | None = None,
    ) -> None:
        self.room_repository = room_repository or RoomRepository()
        self.report_repository = report_repository or ReportRepository()
        self.asset_repository = asset_repository or AssetRepository()
        self.meeting_report_service = meeting_report_service or MeetingReportService()

    def get_report(
        self,
        *,
        db: Session,
        room_id: UUID,
        base_url: str | None,
        user_id: UUID | None = None,
        requested_at: datetime | None = None,
    ) -> ReportResult:
        """팀 프로젝트 리포트 요약과 회의 리포트 HTML 주소.

        리포트가 아직 없으면 이 요청으로 만든다(생성은 BackgroundTasks). 같은 방에 여러 번
        요청해도 같은 리포트 주소를 돌려준다.
        """
        report_requested_at = requested_at or datetime.now(timezone.utc)
        logger.info(
            "[report_started] room_id=%s | user_id=%s | requested_at=%s",
            room_id,
            user_id,
            report_requested_at.isoformat(),
        )

        room = self.room_repository.find_room_by_id(db=db, room_id=room_id)
        if room is None:
            raise NotFoundException(code=ResponseCode.ROOM404)

        participant_counts = (
            self.report_repository.find_participant_utterance_counts(
                db=db,
                room_id=room_id,
                started_at=room.created_at,
                requested_at=report_requested_at,
            )
        )
        total_utterance_count = sum(
            utterance_count
            for _, _, utterance_count in participant_counts
        )
        participants_ratio = [
            ParticipantRatioResponse(
                user_id=user_id,
                nickname=nickname,
                ratio=(
                    round(utterance_count * 100 / total_utterance_count, 2)
                    if total_utterance_count
                    else 0.0
                ),
            )
            for user_id, nickname, utterance_count in participant_counts
        ]

        latest_asset = self.asset_repository.find_latest_ws_sent_2d_asset(
            db=db,
            room_id=room_id,
            requested_at=report_requested_at,
        )

        link = self.meeting_report_service.request_report(
            db,
            room_id=room_id,
            user_id=user_id,
            base_url=base_url,
            requested_at=report_requested_at,
        )

        response = ReportResponse(
            topic=room.topic,
            participants=[nickname for _, nickname, _ in participant_counts],
            participants_ratio=participants_ratio,
            final_2D_image=latest_asset.file_url if latest_asset else None,
            url=link.report_url,
        )
        logger.info(
            "[report_completed] room_id=%s | participant_count=%s | total_utterance_count=%s "
            "| asset_id=%s | report_id=%s | report_status=%s",
            room_id,
            len(participant_counts),
            total_utterance_count,
            latest_asset.asset_id if latest_asset else None,
            link.report_id,
            link.status,
        )
        return ReportResult(response=response, report_id=link.report_id)
