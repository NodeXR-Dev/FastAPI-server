from pydantic import BaseModel
from uuid import UUID
from app.core.validators import NotBlankStr


class FeatureInfo(BaseModel):
    feature_id: UUID
    feature_text: NotBlankStr
    
class FeatureResponse(BaseModel):
    room_id: UUID
    feature_id: UUID
    feature_text: NotBlankStr
    
class FeatureListResponse(BaseModel):
    room_id: UUID
    features: list[FeatureInfo]