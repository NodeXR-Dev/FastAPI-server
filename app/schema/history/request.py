from uuid import UUID

from pydantic import BaseModel, Field


class HistoryRequest(BaseModel):
    room_id: UUID = Field(..., description="조회할 방 ID")