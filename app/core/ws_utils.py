from contextlib import contextmanager
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.schema.websocket.ws_event import WSEvent


@contextmanager
def ws_db_session():
    db: Session = SessionLocal()

    try:
        yield db
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def extract_user_id(event: WSEvent) -> UUID | None:
    if event.user_id is not None:
        return event.user_id

    payload = payload_to_dict(event.payload)
    user_id = payload.get("user_id")

    if user_id is None:
        return None

    if isinstance(user_id, UUID):
        return user_id

    return UUID(str(user_id))


def payload_to_dict(payload: Any) -> dict:
    if payload is None:
        return {}

    if isinstance(payload, dict):
        return payload

    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")

    return dict(payload)


def get_raw_event_type(raw_data: Any) -> str | None:
    if isinstance(raw_data, dict):
        return raw_data.get("event_type")

    return None