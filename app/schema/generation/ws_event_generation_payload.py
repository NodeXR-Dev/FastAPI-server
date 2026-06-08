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