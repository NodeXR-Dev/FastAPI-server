from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, or_, select, update
from sqlalchemy.orm import Session

from app.model.enum import MeetingReportStatus, MemoryStatus, UtteranceState
from app.model.graph import GraphSnapshot
from app.model.memory import (
    DesignFact,
    DesignFactLink,
    DesignFactUtteranceLink,
    SemanticMemory,
    Topic,
    Utterance,
    UtteranceAnnotation,
)
from app.model.report import MeetingReport
from app.model.room import User


class MeetingReportRepository:
    # =========================
    # meeting_reports
    # =========================

    def find_by_id(
        self,
        db: Session,
        *,
        report_id: UUID,
    ) -> MeetingReport | None:
        return db.get(MeetingReport, report_id)

    def find_latest_by_room(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> MeetingReport | None:
        stmt = (
            select(MeetingReport)
            .where(MeetingReport.room_id == room_id)
            .order_by(MeetingReport.report_version.desc())
            .limit(1)
        )
        return db.scalar(stmt)

    def create(
        self,
        db: Session,
        *,
        room_id: UUID,
        report_version: int,
        requested_by_user_id: UUID | None,
        meeting_started_at: datetime | None,
        meeting_ended_at: datetime,
    ) -> MeetingReport:
        report = MeetingReport(
            room_id=room_id,
            report_version=report_version,
            status=MeetingReportStatus.PENDING,
            requested_by_user_id=requested_by_user_id,
            meeting_started_at=meeting_started_at,
            meeting_ended_at=meeting_ended_at,
        )
        db.add(report)
        db.flush()
        return report

    def reset_to_pending(
        self,
        db: Session,
        *,
        report: MeetingReport,
        requested_by_user_id: UUID | None,
    ) -> MeetingReport:
        report.status = MeetingReportStatus.PENDING
        report.requested_by_user_id = requested_by_user_id
        report.error_message = None
        db.flush()
        return report

    def claim_for_generation(
        self,
        db: Session,
        *,
        report_id: UUID,
        stale_before: datetime,
    ) -> bool:
        """PENDING(또는 멈춘 GENERATING)을 GENERATING 으로 바꾼다.

        조건부 UPDATE 한 번이라 동시에 들어온 작업 중 하나만 1행을 바꾼다.
        같은 리포트를 두 번 생성하지 않게 하는 지점이다.
        """
        stmt = (
            update(MeetingReport)
            .where(
                MeetingReport.meeting_report_id == report_id,
                or_(
                    MeetingReport.status == MeetingReportStatus.PENDING,
                    (MeetingReport.status == MeetingReportStatus.GENERATING)
                    & (MeetingReport.updated_at < stale_before),
                ),
            )
            .values(status=MeetingReportStatus.GENERATING)
            .execution_options(synchronize_session=False)
        )
        return db.execute(stmt).rowcount == 1

    def mark_completed(
        self,
        db: Session,
        *,
        report: MeetingReport,
        report_data: str,
        final_asset_id: UUID | None,
        final_graph_snapshot_id: UUID | None,
        generated_at: datetime,
    ) -> MeetingReport:
        report.status = MeetingReportStatus.COMPLETED
        report.report_data = report_data
        report.final_asset_id = final_asset_id
        report.final_graph_snapshot_id = final_graph_snapshot_id
        report.generated_at = generated_at
        report.error_message = None
        db.flush()
        return report

    def mark_failed(
        self,
        db: Session,
        *,
        report: MeetingReport,
        error_message: str,
    ) -> MeetingReport:
        report.status = MeetingReportStatus.FAILED
        report.error_message = error_message
        db.flush()
        return report

    def has_activity_after(
        self,
        db: Session,
        *,
        room_id: UUID,
        after: datetime,
    ) -> bool:
        """리포트 이후 회의가 이어졌는지. 발화나 그래프 스냅샷이 새로 생겼으면 True."""
        utterance_exists = exists().where(
            Utterance.room_id == room_id,
            Utterance.created_at > after,
        )
        snapshot_exists = exists().where(
            GraphSnapshot.room_id == room_id,
            GraphSnapshot.created_at > after,
        )
        return bool(db.scalar(select(or_(utterance_exists, snapshot_exists))))

    # =========================
    # 리포트 생성 입력 (방 단위로 한 번씩 조회해 N+1 을 피한다)
    # =========================

    def find_topics(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> list[Topic]:
        stmt = (
            select(Topic)
            .where(Topic.room_id == room_id)
            .order_by(Topic.created_at.asc(), Topic.topic_id.asc())
        )
        return list(db.scalars(stmt).all())

    def find_discussion_utterances(
        self,
        db: Session,
        *,
        room_id: UUID,
        ended_at: datetime,
    ) -> list[tuple[Utterance, str]]:
        """Topic 에 배정된 회의 발화와 화자 닉네임.

        SKIP 은 호출어로 Agent 에게 건넨 명령("노드베어 이미지 만들어줘")이라
        팀 논의가 아니므로 뺀다.
        """
        stmt = (
            select(Utterance, User.nickname)
            .join(User, User.user_id == Utterance.user_id)
            .where(
                Utterance.room_id == room_id,
                Utterance.topic_id.isnot(None),
                Utterance.created_at <= ended_at,
                or_(
                    Utterance.state.is_(None),
                    Utterance.state != UtteranceState.SKIP,
                ),
            )
            .order_by(Utterance.created_at.asc(), Utterance.utterance_id.asc())
        )
        return [(utterance, nickname) for utterance, nickname in db.execute(stmt).all()]

    def find_facts(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> list[DesignFact]:
        stmt = (
            select(DesignFact)
            .where(
                DesignFact.room_id == room_id,
                DesignFact.topic_id.isnot(None),
            )
            .order_by(DesignFact.created_at.asc(), DesignFact.design_fact_id.asc())
        )
        return list(db.scalars(stmt).all())

    def find_fact_links(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> list[DesignFactLink]:
        stmt = (
            select(DesignFactLink)
            .where(DesignFactLink.room_id == room_id)
            .order_by(DesignFactLink.created_at.asc())
        )
        return list(db.scalars(stmt).all())

    def find_fact_utterance_links(
        self,
        db: Session,
        *,
        fact_ids: list[UUID],
    ) -> list[DesignFactUtteranceLink]:
        if not fact_ids:
            return []
        stmt = (
            select(DesignFactUtteranceLink)
            .where(DesignFactUtteranceLink.design_fact_id.in_(fact_ids))
            .order_by(DesignFactUtteranceLink.created_at.asc())
        )
        return list(db.scalars(stmt).all())

    def find_active_memories(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> list[SemanticMemory]:
        stmt = (
            select(SemanticMemory)
            .where(
                SemanticMemory.room_id == room_id,
                SemanticMemory.topic_id.isnot(None),
                SemanticMemory.status == MemoryStatus.ACTIVE,
            )
            .order_by(
                SemanticMemory.created_at.desc(),
                SemanticMemory.semantic_memory_id.asc(),
            )
        )
        return list(db.scalars(stmt).all())

    def find_annotations(
        self,
        db: Session,
        *,
        utterance_ids: list[UUID],
        model_version: str,
    ) -> list[UtteranceAnnotation]:
        if not utterance_ids:
            return []
        stmt = select(UtteranceAnnotation).where(
            UtteranceAnnotation.utterance_id.in_(utterance_ids),
            UtteranceAnnotation.model_version == model_version,
        )
        return list(db.scalars(stmt).all())

    def find_utterance_similarities(
        self,
        db: Session,
        *,
        utterance_ids: list[UUID],
        embedding: list[float],
    ) -> dict[UUID, float]:
        """발화와 기준 벡터(최종 결정)의 cosine similarity. pgvector 로 계산한다."""
        if not utterance_ids:
            return {}
        distance = Utterance.embedding.cosine_distance(embedding)
        stmt = select(Utterance.utterance_id, distance).where(
            Utterance.utterance_id.in_(utterance_ids),
            Utterance.embedding.isnot(None),
        )
        return {
            utterance_id: max(-1.0, min(1.0, 1.0 - float(cosine_distance)))
            for utterance_id, cosine_distance in db.execute(stmt).all()
        }
