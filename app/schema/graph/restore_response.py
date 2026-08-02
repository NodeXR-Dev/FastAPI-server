from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.model.enum import NodeType


class GraphRestoreCore2DImageResponse(BaseModel):
    asset_id: UUID
    image_url: str
    mime_type: str
    width: int
    height: int


class GraphRestoreNodeResponse(BaseModel):
    node_id: UUID
    type: NodeType
    node_text: str | None = None
    position: list[float] = Field(default_factory=list)
    parent_node_id: UUID | None = None
    used_in_generation: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class GraphRestoreEdgeResponse(BaseModel):
    edge_id: UUID
    from_node_id: UUID
    to_node_id: UUID
    label: str | None = None
    used_in_generation: bool = False


class GraphRestoreSubGraphResponse(BaseModel):
    sub_graph_id: UUID
    root_node_id: UUID | None = None
    nodes: list[GraphRestoreNodeResponse] = Field(default_factory=list)
    edges: list[GraphRestoreEdgeResponse] = Field(default_factory=list)


class GraphRestoreResponse(BaseModel):
    room_id: UUID
    graph_version: int
    core_2d_image: GraphRestoreCore2DImageResponse | None = None
    sub_graphs: list[GraphRestoreSubGraphResponse] = Field(default_factory=list)
