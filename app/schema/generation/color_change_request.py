from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ColorChangeMetadataRequest(BaseModel):
    mime_type: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @field_validator("mime_type")
    @classmethod
    def normalize_mime_type(cls, value: str) -> str:
        return value.strip().lower()


class ColorChangeRequest(BaseModel):
    room_id: UUID
    asset_id: UUID
    metadata: ColorChangeMetadataRequest
