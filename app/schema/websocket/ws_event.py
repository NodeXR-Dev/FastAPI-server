from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from app.core.validators import NotBlankStr
from app.schema.generation.ws_event_generation_payload import Image2DAssetPayload, Model3DAssetPayload
from app.schema.graph.response import NodeGraphResponse
from app.schema.graph.ws_event_edge_payload import EdgeCreatePayload
from app.schema.graph.ws_event_node_payload import NodeMovePayload, NodeUpdatePayload
from app.schema.guide.ws_event_guide_payload import AgentGuidePayload
from app.schema.utterance.ws_event_utterance_payload import AutoUtterancePayload


class WSEvent(BaseModel):
    event_type: NotBlankStr
    room_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)

class Image2DGeneratedWSEvent(WSEvent):
    event_type: Literal["2D_GENERATED"] = "2D_GENERATED"
    payload: Image2DAssetPayload

class Model3DGeneratedWSEvent(WSEvent):
    event_type: Literal["3D_GENERATED"] = "3D_GENERATED"
    payload: Model3DAssetPayload

class AutoUtteranceWSEvent(WSEvent):
    event_type: Literal["UTTERANCE_CREATE"] = "UTTERANCE_CREATE"
    payload: AutoUtterancePayload

class NodeUpdateWSEvent(WSEvent):
    event_type: Literal["NODE_TEXT_UPDATE"] = "NODE_TEXT_UPDATE"
    payload: NodeUpdatePayload

class NodeDeleteWSEvent(WSEvent):
    event_type: Literal["NODE_DELETE"] = "NODE_DELETE"

class NodeMoveWSEvent(WSEvent):
    event_type: Literal["NODE_MOVE"] = "NODE_MOVE"
    payload: NodeMovePayload

class EdgeCreateWSEvent(WSEvent):
    event_type: Literal["EDGE_CREATE"] = "EDGE_CREATE"
    payload: EdgeCreatePayload

class EdgeDeleteWSEvent(WSEvent):
    event_type: Literal["EDGE_DELETE"] = "EDGE_DELETE"

class GraphUpdateWSEvent(WSEvent):
    event_type: Literal["GRAPH_UPDATED"] = "GRAPH_UPDATED"
    payload: NodeGraphResponse

class AgentGuideWSEvent(WSEvent):
    event_type: Literal["AGENT_GUIDE"] = "AGENT_GUIDE"
    payload: AgentGuidePayload