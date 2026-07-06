from uuid import UUID
from pydantic import BaseModel, Field
from app.core.validators import NotBlankStr
from app.model.enum import NodeType

class NodeCreatePayload(BaseModel):
    job_id: UUID
    sub_graph_id: UUID | None = None
    node_text: NotBlankStr
    parent_node_id: UUID | None = None
    position: list[float] = Field(default_factory=list)
    

class NodeUpdatePayload(BaseModel):
    node_id: UUID
    text: NotBlankStr

class NodeMovePayload(BaseModel):
    node_id: UUID
    position: list[float] = Field(default_factory=list)

class NodeDeletePayload(BaseModel):
    node_id: UUID