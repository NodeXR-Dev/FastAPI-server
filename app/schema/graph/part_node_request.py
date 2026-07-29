from uuid import UUID

from pydantic import BaseModel

from app.core.validators import NotBlankStr


class CreatePartNodeRequest(BaseModel):
    room_id: UUID
    text: NotBlankStr
    position: tuple[float, float, float]


class ModifyPartNodeRequest(BaseModel):
    room_id: UUID
    part_node_id: UUID
    part_node_text: NotBlankStr


class DeletePartNodeRequest(BaseModel):
    room_id: UUID
    part_node_id: UUID
