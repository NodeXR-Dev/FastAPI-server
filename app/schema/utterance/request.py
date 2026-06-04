from pydantic import BaseModel, Field
from uuid import UUID
from app.core.validators import NotBlankStr

class CreateNodeUtteranceRequest(BaseModel):
    room_id: UUID
    user_id: UUID
    parent_node_id: UUID | None = None
    parent_node_position: list[float] | None = Field(default=None)
    utterance: NotBlankStr