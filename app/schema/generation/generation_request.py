from uuid import UUID

from pydantic import BaseModel, Field


class Generate2DRequest(BaseModel):
    room_id: UUID

class Generate3DRequest(BaseModel):
    room_id: UUID
    asset_id: UUID | None = None