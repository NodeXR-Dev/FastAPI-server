import time
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import get_logger
from app.core.performance import performance_tracker
from app.repository.topic_repository import TopicRepository
from app.repository.utterance_repository import UtteranceRepository

logger = get_logger(__name__)


class TopicRoutingService:
    def __init__(
        self,
        *,
        topic_repository: TopicRepository | None = None,
        utterance_repository: UtteranceRepository | None = None,
        similarity_threshold: float | None = None,
    ) -> None:
        self.topic_repository = topic_repository or TopicRepository()
        self.utterance_repository = utterance_repository or UtteranceRepository()
        self.similarity_threshold = (
            settings.TOPIC_SIMILARITY_THRESHOLD
            if similarity_threshold is None
            else similarity_threshold
        )

    def route_topic(
        self,
        db: Session,
        *,
        room_id: UUID,
        utterance_id: UUID,
        normalized_text: str,
        embedding: list[float],
        room_locked: bool = False,
    ) -> UUID:
        started_at = time.perf_counter()

        # 같은 room의 동시 centroid 갱신에서 lost update가 생기지 않도록 직렬화한다.
        if not room_locked:
            self.lock_room(db, room_id=room_id)
        match = self.topic_repository.find_most_similar_active_topic(
            db,
            room_id=room_id,
            embedding=embedding,
        )

        if match is None or match.similarity < self.similarity_threshold:
            topic = self.topic_repository.create(
                db,
                room_id=room_id,
                summary=normalized_text,
                centroid_embedding=embedding,
            )
            route_kind = "new"
            similarity = match.similarity if match is not None else None
        else:
            topic = match.topic
            linked_count = self.topic_repository.count_linked_utterances(
                db,
                topic_id=topic.topic_id,
            )
            current_centroid = list(
                topic.centroid_embedding
                if topic.centroid_embedding is not None
                else embedding
            )
            if len(current_centroid) != len(embedding):
                raise ValueError("Topic centroid와 utterance embedding 차원이 다릅니다.")
            denominator = linked_count + 1
            centroid = [
                ((float(current_value) * linked_count) + float(new_value))
                / denominator
                for current_value, new_value in zip(current_centroid, embedding)
            ]
            self.topic_repository.update_centroid(
                db,
                topic=topic,
                centroid_embedding=centroid,
            )
            route_kind = "existing"
            similarity = match.similarity

        self.utterance_repository.update(
            db,
            utterance_id=utterance_id,
            topic_id=topic.topic_id,
        )

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        performance_tracker.record("topic_routing", elapsed_ms)
        logger.info(
            "[topic_routing_completed] room_id=%s | utterance_id=%s | topic_id=%s | route=%s | similarity=%s | elapsed_ms=%.2f",
            room_id,
            utterance_id,
            topic.topic_id,
            route_kind,
            similarity,
            elapsed_ms,
        )
        return topic.topic_id

    def lock_room(self, db: Session, *, room_id: UUID) -> None:
        self.topic_repository.lock_room(db, room_id=room_id)
