from pydantic import BaseModel, Field

from app.core.validators import NotBlankStr
from app.models.enums import NodeType


class ExtractedNode(BaseModel):
    node_text: NotBlankStr
    node_type: NodeType = NodeType.PROPERTY


class ExtractedParentEdge(BaseModel):
    to_node_text: NotBlankStr
    label: NotBlankStr


class ExtractedInternalEdge(BaseModel):
    from_node_text: NotBlankStr
    to_node_text: NotBlankStr
    label: NotBlankStr


class KeywordExtractResult(BaseModel):
    nodes: list[ExtractedNode] = Field(default_factory=list)
    parent_edges: list[ExtractedParentEdge] = Field(default_factory=list)
    internal_edges: list[ExtractedInternalEdge] = Field(default_factory=list)