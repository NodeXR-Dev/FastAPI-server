# app/schemas/ws_generation.py

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class Image2DAssetPayload(BaseModel):
    asset_id: UUID
    mime_type: str
    width: int | None = None
    height: int | None = None
    img_url: str


class Model3DAssetPayload(BaseModel):
    asset_id: UUID
    mime_type: str
    model_url: str
    thumbnail_url: str | None = None


class GeneratedAssetEventPayload(BaseModel):
    job_id: UUID
    target_node_id: UUID | None = None
    asset: Image2DAssetPayload | Model3DAssetPayload


class GenerationFailedPayload(BaseModel):
    job_id: UUID
    target_node_id: UUID | None = None
    code: str
    message: str
    reason: str | None = None


class Image2DGeneratedWSEvent(BaseModel):
    event_type: Literal["2D_GENERATED"] = "2D_GENERATED"
    room_id: UUID
    request_id: UUID | None = None
    user_id: UUID
    payload: GeneratedAssetEventPayload


class Image2DGenerationFailedWSEvent(BaseModel):
    event_type: Literal["2D_GENERATION_FAILED"] = "2D_GENERATION_FAILED"
    room_id: UUID
    request_id: UUID | None = None
    user_id: UUID
    payload: GenerationFailedPayload


class Model3DGeneratedWSEvent(BaseModel):
    event_type: Literal["3D_GENERATED"] = "3D_GENERATED"
    room_id: UUID
    request_id: UUID | None = None
    user_id: UUID
    payload: GeneratedAssetEventPayload


class Model3DGenerationFailedWSEvent(BaseModel):
    event_type: Literal["3D_GENERATION_FAILED"] = "3D_GENERATION_FAILED"
    room_id: UUID
    request_id: UUID | None = None
    user_id: UUID
    payload: GenerationFailedPayload