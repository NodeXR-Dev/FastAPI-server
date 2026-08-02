from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.validators import NotBlankStr
from app.core.response.code import ResponseCode, get_message

from app.model.enum import GraphEventType
from app.schema.generation.ws_event_generation_payload import (
    Image2DAssetPayload,
    Image2DColorChangedPayload,
    Model3DAssetPayload,
)
from app.schema.graph.response import NodeGraphResponse
from app.schema.graph.ws_event_edge_payload import EdgeCreatePayload, EdgeDeletePayload
from app.schema.graph.ws_event_node_payload import NodeCreatePayload, NodeDeletePayload, NodeMovePayload, NodeUpdatePayload
from app.schema.utterance.ws_event_utterance_payload import AutoUtterancePayload
from app.schema.agent.ws_event_agent_payload import AgentGuidePayload


class WSEvent(BaseModel):
    event_type: NotBlankStr
    room_id: UUID
    user_id: UUID | None=None
    job_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

class WSConnectWSEvent(WSEvent):
    event_type: Literal["WS_CONNECT"] = "WS_CONNECT"

class Image2DGeneratedWSEvent(WSEvent):
    event_type: Literal["2D_GENERATED"] = "2D_GENERATED"
    payload: Image2DAssetPayload


class Image2DColorChangedWSEvent(BaseModel):
    event_type: Literal["2D_COLOR_CHANGED"] = "2D_COLOR_CHANGED"
    room_id: UUID
    job_id: UUID
    payload: Image2DColorChangedPayload

class Model3DGeneratedWSEvent(BaseModel):
    event_type: Literal["3D_GENERATED"] = "3D_GENERATED"
    room_id: UUID
    job_id: UUID | None = None
    payload: Model3DAssetPayload


class AutoUtteranceWSEvent(WSEvent):
    event_type: Literal["UTTERANCE_CREATE"] = "UTTERANCE_CREATE"
    payload: AutoUtterancePayload


class AgentGuideWSEvent(WSEvent):
    event_type: Literal["AGENT_GUIDE"] = "AGENT_GUIDE"
    payload: AgentGuidePayload

class NodeCreateWSEvent(WSEvent):
    event_type: GraphEventType.NODE_CREATE
    payload: NodeCreatePayload

class NodeTextUpdateWSEvent(WSEvent):
    event_type: GraphEventType.NODE_TEXT_UPDATE
    payload: NodeUpdatePayload


class NodeDeleteWSEvent(WSEvent):
    event_type: GraphEventType.NODE_DELETE
    payload: NodeDeletePayload


class NodeMoveWSEvent(WSEvent):
    event_type: GraphEventType.NODE_MOVE
    payload: NodeMovePayload


class EdgeCreateWSEvent(WSEvent):
    event_type: GraphEventType.EDGE_CREATE
    payload: EdgeCreatePayload


class EdgeDeleteWSEvent(WSEvent):
    event_type: GraphEventType.EDGE_DELETE
    payload: EdgeDeletePayload


class GraphUpdateWSEvent(WSEvent):
    event_type: Literal["GRAPH_UPDATED"] = "GRAPH_UPDATED"
    payload: NodeGraphResponse
