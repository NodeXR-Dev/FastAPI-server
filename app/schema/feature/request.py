from uuid import UUID

from pydantic import BaseModel, field_validator

from app.core.validators import NotBlankStr


class GenerateFeaturesRequest(BaseModel):
    room_id: UUID
    user_id: UUID
    job_id: UUID
    feature_text: NotBlankStr

    @field_validator("feature_text")
    @classmethod
    def validate_meaningful_feature_text(cls, value: str) -> str:
        if not any(character.isalnum() for character in value):
            raise ValueError("feature_text에는 의미 있는 텍스트가 포함되어야 합니다.")
        return value


class ModifyFeatureRequest(BaseModel):
    room_id: UUID
    feature_id: UUID
    feature_text: NotBlankStr


class DeleteFeatureRequest(BaseModel):
    room_id: UUID
    feature_id: UUID
