from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.core.validators import NotBlankStr


# =========================
# Request
# =========================

class CreateRoomRequest(BaseModel):
    room_topic: NotBlankStr
    password: NotBlankStr
    nickname: NotBlankStr


class EnterRoomRequest(BaseModel):
    room_id: UUID
    nickname: NotBlankStr
    password: NotBlankStr