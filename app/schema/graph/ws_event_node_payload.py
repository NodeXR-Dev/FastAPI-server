from uuid import UUID
from pydantic import BaseModel, Field
from app.core.validators import NotBlankStr

class NodeCreatePayload(BaseModel):
    node_text: NotBlankStr
    parent_node_id: UUID

class NodeUpdatePayload(BaseModel):
    node_id: UUID
    text: NotBlankStr

class NodeMovePayload(BaseModel):
    node_id: UUID
    position: list[float] = Field(default_factory=list)

class NodeDeletePayload(BaseModel):
    node_id: UUID