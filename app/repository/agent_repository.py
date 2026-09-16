from uuid import UUID

from sqlalchemy.orm import Session

from app.model.agent import AgentAlert
from app.model.enum import AlertStatus, AlertType, DialogueMove, Stance
from app.model.memory import UtteranceAnnotation


class AgentRepository:
    def find_duplicate_alert(
        self,
        db: Session,
        *,
        triggering_utterance_id: UUID,
        related_fact_id: UUID,
        alert_type: AlertType,
    ) -> AgentAlert | None:
        return (
            db.query(AgentAlert)
            .filter(
                AgentAlert.triggering_utterance_id == triggering_utterance_id,
                AgentAlert.related_fact_id == related_fact_id,
                AgentAlert.alert_type == alert_type,
            )
            .first()
        )

    def create_alert(
        self,
        db: Session,
        *,
        room_id: UUID,
        topic_id: UUID | None,
        triggering_utterance_id: UUID,
        related_fact_id: UUID,
        alert_type: AlertType,
        message: str,
    ) -> AgentAlert:
        alert = AgentAlert(
            room_id=room_id,
            topic_id=topic_id,
            triggering_utterance_id=triggering_utterance_id,
            related_fact_id=related_fact_id,
            alert_type=alert_type,
            status=AlertStatus.PENDING,
            message=message,
        )
        db.add(alert)
        db.flush()
        return alert

    def upsert_annotation(
        self,
        db: Session,
        *,
        utterance_id: UUID,
        dialogue_move: DialogueMove,
        stance: Stance,
        confidence: float,
        model_version: str,
        target_fact_id: UUID | None = None,
    ) -> UtteranceAnnotation:
        """같은 발화를 같은 스키마 버전으로 다시 분석하면 덮어쓴다."""
        annotation = (
            db.query(UtteranceAnnotation)
            .filter(
                UtteranceAnnotation.utterance_id == utterance_id,
                UtteranceAnnotation.model_version == model_version,
            )
            .first()
        )
        if annotation is None:
            annotation = UtteranceAnnotation(
                utterance_id=utterance_id,
                model_version=model_version,
            )
            db.add(annotation)
        annotation.dialogue_move = dialogue_move
        annotation.stance = stance
        annotation.confidence = confidence
        annotation.target_fact_id = target_fact_id
        db.flush()
        return annotation
