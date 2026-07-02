from uuid import UUID
from sqlalchemy.orm import Session
from app.core.logger import get_logger

logger = get_logger(__name__)


class AutoUtteranceService:
    """
    자동 발화 처리 서비스.

    UTTERANCE_CREATE 이벤트를 받아서:
    - utterances 저장
    - 필요 시 graph 업데이트
    - 필요 시 agent guide 생성

    반환값:
    - Server → Unity로 보낼 WS 이벤트 목록
    - router가 room broadcast 처리
    """

    def __init__(self, db: Session):
        self.db = db

    async def handle_auto_utterance(
        self,
        *,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> list[dict]:
        utterance = payload["utterance"]

        logger.info(
            "[auto_utterance] room_id=%s | user_id=%s | utterance=%s",
            room_id,
            user_id,
            utterance,
        )

        # TODO:
        # 1. utterances 저장
        # 2. normalized_text 생성
        # 3. 의미 있는 발화인지 판단
        # 4. topic drift 판단
        # 5. graph 반영 필요 시 graph 생성/업데이트
        # 6. guide 필요 시 AGENT_GUIDE 이벤트 생성

        utterance_id = "created-utterance-uuid"

        events: list[dict] = []

        # 자동 발화 저장 완료 사실도 모든 클라이언트가 알아야 한다면 broadcast.
        # 필요 없으면 이 이벤트는 빼도 됨.
        events.append(
            {
                "event_type": "UTTERANCE_CREATED",
                "room_id": room_id,
                "user_id": user_id,
                "payload": {
                    "utterance_id": utterance_id,
                    "utterance": utterance,
                },
            }
        )

        # graph 수정이 필요한 경우에만 추가
        # events.append(
        #     {
        #         "event_type": "GRAPH_UPDATED",
        #         "room_id": room_id,
        #         "request_id": request_id,
        #         "user_id": None,
        #         "payload": {
        #             "graph": {...}
        #         },
        #     }
        # )

        # 발화 가이드가 필요한 경우에만 추가
        # events.append(
        #     {
        #         "event_type": "AGENT_GUIDE",
        #         "room_id": room_id,
        #         "request_id": request_id,
        #         "user_id": None,
        #         "payload": {
        #             "guide_id": "...",
        #             "guide_type": "...",
        #             "message": "...",
        #             "evidence": {...}
        #         },
        #     }
        # )

        return events