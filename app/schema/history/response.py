from uuid import UUID
from typing import Any

from pydantic import BaseModel

class HistoryResponse(BaseModel):
    room_id: UUID
    history: list[dict[str, Any]]