from uuid import UUID

from sqlalchemy.orm import Session

from app.model.agent import AgentAlert
from app.model.enum import AlertStatus, AlertType


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
