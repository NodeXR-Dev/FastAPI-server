from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.model.graph import Node
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
    ) -> list[tuple[UUID, str, int]]:
        stmt = (
            select(
                RoomMember.user_id,
                User.nickname,
                func.count(Utterance.utterance_id),
            )
            .join(User, User.user_id == RoomMember.user_id)
            .outerjoin(
                Utterance,
                and_(
                    Utterance.room_id == RoomMember.room_id,
                    Utterance.user_id == RoomMember.user_id,
                    Utterance.created_at >= started_at,
                    Utterance.created_at <= requested_at,
                ),
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

    def find_keywords(
        self,
        db: Session,
        *,
        room_id: UUID,
        limit: int = 8,
    ) -> list[str]:
        """리포트 상단의 '키워드 정리' 칩에 쓸 문구.

        그래프 노드의 텍스트를 그대로 쓴다. 노드는 발화 추출 단계에서 이미
        "짧은 명사구" 로 만들어지므로(app/ai/prompts/keyword_prompt.py) 추가
        LLM 호출 없이 칩으로 쓸 수 있다.

        삭제된 노드(deleted_at)는 제외하고, 같은 문구가 여러 번 나오면 한 번만 센다.

        nodes 에 생성 시각 컬럼이 없어 "최신순" 으로는 자를 수 없다. 호출마다 순서가
        흔들리지 않도록 문구 사전순으로 고정한다(node_id 는 UUID 라 Postgres 에서
        max() 집계가 되지 않고, 정렬해도 의미가 없다).
        """
        stmt = (
            select(Node.node_text)
            .where(
                Node.room_id == room_id,
                Node.deleted_at.is_(None),
                Node.node_text.isnot(None),
                func.length(func.trim(Node.node_text)) > 0,
            )
            .distinct()
            .order_by(Node.node_text.asc())
            .limit(limit)
        )
        return [text.strip() for (text,) in db.execute(stmt).all()]
