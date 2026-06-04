from uuid import UUID
from app.model.enum import NodeType
from pydantic import BaseModel, Field
from typing import Any
from app.core.validators import NotBlankStr

class GraphNodeResponse(BaseModel):
    node_id: UUID
    type: NodeType
    node_text: NotBlankStr
    position: list[float] = Field(default_factory=list)
    parent_node_id: UUID | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    


class GraphEdgeResponse(BaseModel):
    edge_id: UUID
    from_node_id: UUID
    to_node_id: UUID
    label: NotBlankStr 


class GraphResponse(BaseModel):
    graph_version: int
    nodes: list[GraphNodeResponse] = Field(default_factory=list)
    edges: list[GraphEdgeResponse] = Field(default_factory=list)


class NodeGraphResponse(BaseModel):
    room_id: UUID
    graph: GraphResponse