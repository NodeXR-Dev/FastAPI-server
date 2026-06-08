from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from app.core.logger import get_logger

logger = get_logger(__name__)


class AgentGuideService:
    """
    발화 가이드 생성 서비스.

    guide_type 예:
    - DECISION_CONFLICT
    - CONSTRAINT_VIOLATION
    - LONG_UNRESOLVED_CONFLICT
    - TOPIC_SHIFT_WITH_UNRESOLVED_CONFLICT
    - DECISION_RATIONALE_RECALL
    - CONSTRAINT_RATIONALE_RECALL
    - CONFLICT_RATIONALE_RECALL
    - SIMILAR_CONFLICT_REPEATED
    - PART_GLOBAL_DECISION_CONFLICT

    반환값:
    - AGENT_GUIDE 이벤트 dict
    - router에서 room broadcast
    """

    def __init__(self, db: Session):
        self.db = db

    async def create_guide(
        self,
        *,
        guide_type: str,
        room_id: UUID,
        user_id: UUID | None,
        request_id: UUID | None,
        payload: dict,
    ) -> dict:
        logger.info(
            "[agent_guide] guide_type=%s | room_id=%s | user_id=%s",
            guide_type,
            room_id,
            user_id,
        )

        # TODO:
        # guide_type별 DB 조회
        #
        # DECISION_CONFLICT:
        # - design_facts에서 fact_type=DECISION, status=CONFIRMED/ACTIVE 조회
        #
        # CONSTRAINT_VIOLATION:
        # - design_facts에서 fact_type=CONSTRAINT 조회
        #
        # LONG_UNRESOLVED_CONFLICT:
        # - semantic_memories 또는 design_facts에서 unresolved conflict 조회
        #
        # TOPIC_SHIFT_WITH_UNRESOLVED_CONFLICT:
        # - 이전 topic_id의 CONFLICT/ISSUE memory 조회
        #
        # DECISION_RATIONALE_RECALL:
        # - DECISION과 연결된 RATIONALE/ARGUMENT 조회
        #
        # CONSTRAINT_RATIONALE_RECALL:
        # - CONSTRAINT와 연결된 RATIONALE 조회
        #
        # CONFLICT_RATIONALE_RECALL:
        # - CONFLICT와 연결된 ARGUMENT_FOR/AGAINST 조회
        #
        # SIMILAR_CONFLICT_REPEATED:
        # - semantic_memories(memory_type=CONFLICT) embedding 검색
        #
        # PART_GLOBAL_DECISION_CONFLICT:
        # - All scope DECISION + part scope proposal 조회

        guide_id = uuid4()

        return {
            "event_type": "AGENT_GUIDE",
            "room_id": room_id,
            "request_id": request_id,
            "user_id": None,
            "payload": {
                "guide_id": guide_id,
                "guide_type": guide_type,
                "message": "발화 가이드 메시지입니다.",
                "evidence": {
                    "current_utterance": {
                        "text": None,
                        "user_id": None,
                        "created_at": None,
                    },
                    "related_utterances": [],
                    "related_facts": [],
                    "related_memories": [],
                },
            },
        }