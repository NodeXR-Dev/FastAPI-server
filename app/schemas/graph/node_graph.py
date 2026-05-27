from pydantic import BaseModel


class GraphNodeResponse(BaseModel):
    node_id: str
    type: str
    node_text: str | None
    position: list[float]
    parent_node_id: str | None
    data: dict


class GraphEdgeResponse(BaseModel):
    edge_id: str
    from_node_id: str
    to_node_id: str
    label: str


class GraphResponse(BaseModel):
    graph_version: int
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]