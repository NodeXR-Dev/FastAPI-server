from uuid import UUID
from typing import Any

from pydantic import BaseModel, Field

from app.core.validators import NotBlankStr
from app.model.enum import NodeType


class Core2DImageResponse(BaseModel):
    asset_id: UUID
    image_url: str
    mime_type: str
    width: int
    height: int


class GraphNodeResponse(BaseModel):
    node_id: UUID
    type: NodeType
    node_text: NotBlankStr | None = None
    position: list[float] = Field(default_factory=list)
    parent_node_id: UUID | None = None
    used_in_generation: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeResponse(BaseModel):
    edge_id: UUID
    from_node_id: UUID
    to_node_id: UUID
    label: NotBlankStr | None = None
    used_in_generation: bool = False


# =========================
# Internal graph build result
# =========================
# GraphBuildService / GraphRepository.save_graph_from_response 에서 사용
# LLM 추출 결과를 DB에 저장하기 전 임시 flat graph 형태로 들고 있기 위한 schema
class GraphResponse(BaseModel):
    graph_version: int = 1
    nodes: list[GraphNodeResponse] = Field(default_factory=list)
    edges: list[GraphEdgeResponse] = Field(default_factory=list)


class SubGraphResponse(BaseModel):
    sub_graph_id: UUID
    root_node_id: UUID | None = None
    nodes: list[GraphNodeResponse] = Field(default_factory=list)
    edges: list[GraphEdgeResponse] = Field(default_factory=list)


class GraphSnapshotResponse(BaseModel):
    graph_version: int
    core_2d_image: Core2DImageResponse | None = None
    sub_graphs: list[SubGraphResponse] = Field(default_factory=list)


class NodeGraphResponse(BaseModel):
    room_id: UUID
    graph_version: int
    core_2d_image: Core2DImageResponse | None = None
    sub_graphs: list[SubGraphResponse] = Field(default_factory=list)


class NodeGraphHistoryResponse(BaseModel):
    history: list[GraphSnapshotResponse] = Field(default_factory=list)