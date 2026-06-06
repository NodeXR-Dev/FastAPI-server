from pydantic import BaseModel
from uuid import UUID
from app.core.validators import NotBlankStr


class CreateFeatureRequest(BaseModel):
    room_id: UUID
    feature_text: NotBlankStr
    
class ModifyFeatureRequest(BaseModel):
    room_id: UUID
    feature_id: UUID
    feature_text: NotBlankStr

class DeleteFeatureRequest(BaseModel):
    room_id: UUID
    feature_id: UUID