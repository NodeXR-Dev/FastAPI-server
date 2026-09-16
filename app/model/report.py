import uuid

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.model.enum import MeetingReportStatus


class MeetingReport(Base):
    """회의 종료 시점에 한 번 만들어 두는 리포트.

    Topic별 결과(결정, Decision Journey, 기여도)는 report_data 에 JSON 으로 통째로
    싣는다. 리포트는 만들어진 뒤 바뀌지 않는 스냅샷이고 Topic 단위로 따로 조회하거나
    수정하는 경로가 없어서, 테이블을 나누면 조인만 늘어난다. graph_snapshots.snapshot_data
    와 같은 방식(Text 에 JSON 문자열)이다.

    같은 방을 다시 열고 회의를 이어가면 report_version 을 올려 새 행을 만든다.
    """

    __tablename__ = "meeting_reports"

    meeting_report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id"),
        nullable=False,
    )

    report_version: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[MeetingReportStatus] = mapped_column(
        Enum(MeetingReportStatus, name="meeting_report_status"),
        nullable=False,
        default=MeetingReportStatus.PENDING,
    )

    # 종료를 요청한 사용자. 완료 WS 를 이 사용자에게만 보낸다.
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id"),
    )

    final_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.asset_id"),
    )

    # 최종 2D 이미지를 만들 때 실제로 입력된 스냅샷. 회의 종료 시점의 최신 스냅샷이 아니다.
    final_graph_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_snapshots.graph_snapshot_id"),
    )

    meeting_started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    # 종료 요청 시각. 이 시각 이후의 발화는 이 리포트에 넣지 않는다.
    meeting_ended_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    report_data: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)

    generated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "room_id",
            "report_version",
            name="uq_meeting_reports_room_version",
        ),
        Index("ix_meeting_reports_room_id", "room_id"),
        Index("ix_meeting_reports_status", "status"),
    )
