from datetime import datetime

from pydantic import BaseModel
from uuid import UUID
from app.core.validators import NotBlankStr
from app.model.enum import RoomMemberRole, RoomMemberState

class CreateRoomResult(BaseModel):
    room_id: UUID
    room_topic: str
    password: str
    leader: str
    created_at: datetime


class RoomUserResponse(BaseModel):
    user_id: UUID
    nickname: str


class RoomListItemResponse(BaseModel):
    room_id: UUID
    room_topic: str
    users: list[RoomUserResponse]
    created_at: datetime


class RoomListResult(BaseModel):
    rooms: list[RoomListItemResponse]


class RoomInfoUserResponse(BaseModel):
    user_id: UUID
    nickname: str
    leader: bool


class RoomInfoResult(BaseModel):
    room_id: UUID
    room_topic: str
    users: list[RoomInfoUserResponse]


class EnterRoomResult(BaseModel):
    room_id: UUID
    user_id: UUID