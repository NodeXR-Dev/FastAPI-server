from uuid import UUID
from pydantic import BaseModel, Field
from app.core.validators import NotBlankStr


class NodeUpdatePayload(BaseModel):
    node_id: UUID
    text: NotBlankStr

class NodeMovePayload(BaseModel):
    node_id: UUID
    position: list[float] = Field(default_factory=list)