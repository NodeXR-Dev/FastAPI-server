from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class WSEventRequest(BaseModel):
    """
    Unity → Server WebSocket 요청 공통 schema
    """
    event_type: str
    room_id: UUID
    user_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WSErrorResponse(BaseModel):
    """
    Server → Unity WebSocket 에러 schema
    """
    event_type: str = "ERROR"
    room_id: UUID
    user_id: UUID | None = None
    payload: dict[str, Any]