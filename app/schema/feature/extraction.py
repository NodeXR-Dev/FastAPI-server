from pydantic import BaseModel, Field

from app.core.validators import NotBlankStr


class ExtractedFeature(BaseModel):
    text: NotBlankStr


class FeatureExtractionResult(BaseModel):
    features: list[ExtractedFeature] = Field(min_length=1)
