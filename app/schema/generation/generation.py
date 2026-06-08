# app/schemas/generation.py

from uuid import UUID

from pydantic import BaseModel, Field


class Generate2DRequest(BaseModel):
    room_id: UUID
    user_id: UUID
    prompt: str = Field(min_length=1)
    target_node_id: UUID | None = None


class Generate3DRequest(BaseModel):
    room_id: UUID
    user_id: UUID
    prompt: str = Field(min_length=1)
    source_asset_id: UUID | None = None
    target_node_id: UUID | None = None


class GenerationAcceptedResult(BaseModel):
    job_id: UUID
    status: str = "PENDING"