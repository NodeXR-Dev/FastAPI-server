from datetime import datetime

from pydantic import BaseModel
from uuid import UUID

class CreateRoomResponse(BaseModel):
    room_id: UUID
    room_topic: str
    password: str
    leader: str
    created_at: datetime


class RoomUserResponse(BaseModel):
    user_id: UUID
    nickname: str


class RoomListItemResult(BaseModel):
    room_id: UUID
    room_topic: str
    users: list[RoomUserResponse]
    created_at: datetime


class RoomListResponse(BaseModel):
    rooms: list[RoomListItemResult]


class RoomInfoUserResult(BaseModel):
    user_id: UUID
    nickname: str
    leader: bool


class RoomInfoResponse(BaseModel):
    room_id: UUID
    room_topic: str
    users: list[RoomInfoUserResult]


class EnterRoomResponse(BaseModel):
    room_id: UUID
    user_id: UUID

class ExitRoomResponse(BaseModel):
    room_id: UUID
    user_id: UUID