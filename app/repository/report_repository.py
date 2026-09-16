from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.model.enum import UtteranceState
from app.model.memory import Utterance
from app.model.room import RoomMember, User


class ReportRepository:
    def find_participant_utterance_counts(
        self,
        db: Session,
        *,
        room_id: UUID,
        started_at: datetime,
        requested_at: datetime,
        exclude_agent_commands: bool = False,
    ) -> list[tuple[UUID, str, int]]:
        utterance_conditions = [
            Utterance.room_id == RoomMember.room_id,
            Utterance.user_id == RoomMember.user_id,
            Utterance.created_at >= started_at,
            Utterance.created_at <= requested_at,
        ]
        if exclude_agent_commands:
            # SKIP 은 호출어로 Agent 에게 건넨 명령이라 회의 발화로 세지 않는다.
            utterance_conditions.append(
                or_(Utterance.state.is_(None), Utterance.state != UtteranceState.SKIP)
            )
        stmt = (
            select(
                RoomMember.user_id,
                User.nickname,
                func.count(Utterance.utterance_id),
            )
            .join(User, User.user_id == RoomMember.user_id)
            .outerjoin(
                Utterance,
                and_(*utterance_conditions),
            )
            .where(RoomMember.room_id == room_id)
            .group_by(RoomMember.user_id, User.nickname)
            .order_by(User.nickname.asc(), RoomMember.user_id.asc())
        )
        return [
            (user_id, nickname, int(utterance_count))
            for user_id, nickname, utterance_count in db.execute(stmt).all()
        ]

    def find_last_utterance_at(
        self,
        db: Session,
        *,
        room_id: UUID,
        started_at: datetime,
        requested_at: datetime,
    ) -> datetime | None:
        """방의 마지막 발화 시각. 회의 '종료 시각' 으로 쓴다.

        rooms 에 종료 컬럼이 없어 예전에는 리포트 요청 시각을 종료로 봤는데,
        방을 만들어두고 한참 뒤에 리포트를 열면 회의 시간이 실제보다 훨씬 길게
        나온다(시드 방 실측: 45,955분). 마지막 발화가 실제 회의가 끝난 시점에
        가장 가깝다. 발화가 하나도 없으면 None 을 돌려주고 호출부가 판단한다.
        """
        stmt = select(func.max(Utterance.created_at)).where(
            Utterance.room_id == room_id,
            Utterance.created_at >= started_at,
            Utterance.created_at <= requested_at,
        )
        return db.execute(stmt).scalar_one_or_none()
