from uuid import UUID
from pydantic import BaseModel
from app.core.validators import NotBlankStr


class AutoUtterancePayload(BaseModel):
    user_id: UUID
    utterance: NotBlankStr
    