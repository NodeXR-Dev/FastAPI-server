from uuid import UUID
from pydantic import BaseModel
from app.core.validators import NotBlankStr

class CreateRoomRequest(BaseModel):
    room_topic: NotBlankStr
    # 비밀번호는 선택이다. 생략하면 누구나 들어올 수 있는 공개 방이 된다.
    # (VR 로비에서 비밀번호를 입력받기 어려워 빈 값이 그대로 올라온다)
    password: str | None = None
    nickname: NotBlankStr


class EnterRoomRequest(BaseModel):
    room_id: UUID
    nickname: NotBlankStr
    # 공개 방에 들어올 때는 비밀번호를 보내지 않는다.
    password: str | None = None

class ExitRoomRequest(BaseModel):
    room_id: UUID
    nickname: NotBlankStr