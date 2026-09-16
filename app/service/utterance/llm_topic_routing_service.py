"""LLM으로 발화의 topic을 정하고 구조 서술까지 한 번에 받는다.

임베딩 코사인 유사도만으로는 주제를 가르지 못한다는 실측 결과에 따른 경로다
(docs/topic-threshold-measurement.md). 구조 서술(dialogue_move/stance)을 같은
호출에 합쳐 LLM 호출 수를 늘리지 않는다.

LLM이 실패하면 기존 임베딩 방식으로 떨어진다. 주제 배정은 발화 저장의 전제라
여기서 예외가 나면 발화 자체를 잃는다.
"""

from dataclasses import dataclass
from uuid import UUID

from langchain_core.language_models import BaseChatModel
from sqlalchemy.orm import Session

from app.agent.llm.provider import get_agent_llm
from app.agent.prompt.topic_prompt import UTTERANCE_TOPIC_AND_STRUCTURE_PROMPT
from app.agent.schema.realtime_agent_schema import (
    AnnotationDraft,
    UtteranceTopicAndStructureResult,
)
from app.core.config import settings
from app.core.logger import get_logger
from app.repository.topic_repository import TopicRepository
from app.repository.utterance_repository import UtteranceRepository
from app.service.utterance.topic_routing_service import TopicRoutingService

logger = get_logger(__name__)


@dataclass(frozen=True)
class TopicRoutingOutcome:
    topic_id: UUID
    annotation: AnnotationDraft | None
    route_kind: str


class LlmTopicRoutingService:
    def __init__(
        self,
        *,
        llm: BaseChatModel | None = None,
        topic_repository: TopicRepository | None = None,
        utterance_repository: UtteranceRepository | None = None,
        fallback_service: TopicRoutingService | None = None,
        recent_utterance_limit: int | None = None,
    ) -> None:
        model = llm or get_agent_llm()
        self.chain = (
            UTTERANCE_TOPIC_AND_STRUCTURE_PROMPT
            | model.with_structured_output(UtteranceTopicAndStructureResult)
        ).with_config(run_name="Topic Routing And Structure")
        self.topic_repository = topic_repository or TopicRepository()
        self.utterance_repository = utterance_repository or UtteranceRepository()
        self.fallback_service = fallback_service or TopicRoutingService()
        self.recent_utterance_limit = (
            settings.TOPIC_ROUTING_RECENT_UTTERANCES
            if recent_utterance_limit is None
            else recent_utterance_limit
        )

    async def route(
        self,
        db: Session,
        *,
        room_id: UUID,
        utterance_id: UUID,
        normalized_text: str,
        embedding: list[float],
        room_locked: bool = False,
    ) -> TopicRoutingOutcome:
        if not room_locked:
            self.fallback_service.lock_room(db, room_id=room_id)

        topics = self.topic_repository.find_active_topics(db, room_id=room_id)
        if not topics:
            topic = self.topic_repository.create(
                db,
                room_id=room_id,
                summary=normalized_text,
                centroid_embedding=embedding,
            )
            self.utterance_repository.update(
                db,
                utterance_id=utterance_id,
                topic_id=topic.topic_id,
            )
            return TopicRoutingOutcome(topic.topic_id, None, "first")

        try:
            decision = await self._decide(
                db,
                room_id=room_id,
                utterance_id=utterance_id,
                normalized_text=normalized_text,
                topics=topics,
            )
        except Exception as error:
            logger.exception(
                "[llm_topic_routing_failed] room_id=%s | utterance_id=%s | error=%s",
                room_id,
                utterance_id,
                str(error),
            )
            topic_id = self.fallback_service.route_topic(
                db,
                room_id=room_id,
                utterance_id=utterance_id,
                normalized_text=normalized_text,
                embedding=embedding,
                room_locked=True,
            )
            return TopicRoutingOutcome(topic_id, None, "embedding_fallback")

        annotation = AnnotationDraft(
            dialogue_move=decision.dialogue_move,
            stance=decision.stance,
            confidence=decision.confidence,
            model_version=settings.AGENT_ANNOTATION_SCHEMA_VERSION,
        )

        if 1 <= decision.topic_number <= len(topics):
            topic = topics[decision.topic_number - 1]
            self._extend_centroid(db, topic=topic, embedding=embedding)
            route_kind = "existing"
        else:
            topic = self.topic_repository.create(
                db,
                room_id=room_id,
                summary=decision.new_topic_summary or normalized_text,
                centroid_embedding=embedding,
            )
            route_kind = "new"

        self.utterance_repository.update(
            db,
            utterance_id=utterance_id,
            topic_id=topic.topic_id,
        )
        logger.info(
            "[llm_topic_routing_completed] room_id=%s | utterance_id=%s | topic_id=%s "
            "| route=%s | candidate_count=%s | dialogue_move=%s",
            room_id,
            utterance_id,
            topic.topic_id,
            route_kind,
            len(topics),
            decision.dialogue_move,
        )
        return TopicRoutingOutcome(topic.topic_id, annotation, route_kind)

    async def _decide(
        self,
        db: Session,
        *,
        room_id: UUID,
        utterance_id: UUID,
        normalized_text: str,
        topics: list,
    ) -> UtteranceTopicAndStructureResult:
        topic_index = {
            topic.topic_id: number for number, topic in enumerate(topics, start=1)
        }
        recent = self.utterance_repository.find_recent_by_room(
            db,
            room_id=room_id,
            limit=self.recent_utterance_limit,
            exclude_utterance_id=utterance_id,
        )
        topics_block = "\n".join(
            f"{number}. {topic.summary or '(요약 없음)'}"
            for number, topic in enumerate(topics, start=1)
        )
        recent_block = (
            "\n".join(
                f"- (topic {topic_index.get(item.topic_id, '?')}) "
                f"{item.normalized_text or item.original_text}"
                for item in recent
            )
            or "- (없음)"
        )
        result = await self.chain.ainvoke(
            {
                "topics": topics_block,
                "recent": recent_block,
                "utterance": normalized_text,
            },
        )
        return (
            result
            if isinstance(result, UtteranceTopicAndStructureResult)
            else UtteranceTopicAndStructureResult.model_validate(result)
        )

    def _extend_centroid(self, db: Session, *, topic, embedding: list[float]) -> None:
        """centroid는 계속 갱신한다. 배치 재분할과 fallback이 아직 이 값을 쓴다."""
        linked = self.topic_repository.count_linked_utterances(
            db,
            topic_id=topic.topic_id,
        )
        current = list(
            topic.centroid_embedding
            if topic.centroid_embedding is not None
            else embedding
        )
        if len(current) != len(embedding):
            return
        denominator = linked + 1
        self.topic_repository.update_centroid(
            db,
            topic=topic,
            centroid_embedding=[
                ((float(old) * linked) + float(new)) / denominator
                for old, new in zip(current, embedding)
            ],
        )
