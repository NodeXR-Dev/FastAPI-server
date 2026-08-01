from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.model.enum import TopicStatus
from app.model.memory import Topic, Utterance
from app.model.room import Room


@dataclass(frozen=True)
class TopicMatch:
    topic: Topic
    similarity: float


class TopicRepository:
    def lock_room(self, db: Session, *, room_id: UUID) -> Room | None:
        return (
            db.query(Room)
            .filter(Room.room_id == room_id)
            .with_for_update()
            .first()
        )

    def find_most_similar_active_topic(
        self,
        db: Session,
        *,
        room_id: UUID,
        embedding: list[float],
    ) -> TopicMatch | None:
        distance = Topic.centroid_embedding.cosine_distance(embedding)
        row = (
            db.query(Topic, distance.label("cosine_distance"))
            .filter(
                Topic.room_id == room_id,
                Topic.status == TopicStatus.ACTIVE,
                Topic.centroid_embedding.isnot(None),
            )
            .order_by(distance.asc(), Topic.created_at.asc())
            .first()
        )
        if row is None:
            return None

        topic, cosine_distance = row
        similarity = max(-1.0, min(1.0, 1.0 - float(cosine_distance)))
        return TopicMatch(topic=topic, similarity=similarity)

    def create(
        self,
        db: Session,
        *,
        room_id: UUID,
        summary: str,
        centroid_embedding: list[float],
    ) -> Topic:
        topic = Topic(
            room_id=room_id,
            summary=summary,
            status=TopicStatus.ACTIVE,
            centroid_embedding=centroid_embedding,
        )
        db.add(topic)
        db.flush()
        return topic

    def count_linked_utterances(
        self,
        db: Session,
        *,
        topic_id: UUID,
    ) -> int:
        return int(
            db.query(func.count(Utterance.utterance_id))
            .filter(Utterance.topic_id == topic_id)
            .scalar()
            or 0
        )

    def update_centroid(
        self,
        db: Session,
        *,
        topic: Topic,
        centroid_embedding: list[float],
    ) -> Topic:
        topic.centroid_embedding = centroid_embedding
        db.flush()
        return topic
