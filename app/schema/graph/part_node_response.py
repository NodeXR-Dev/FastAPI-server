from uuid import UUID

from pydantic import BaseModel

from app.core.validators import NotBlankStr


class PartNodeResponse(BaseModel):
    room_id: UUID
    part_node_id: UUID
    part_node_text: NotBlankStr


class DeletePartNodeResponse(BaseModel):
    room_id: UUID
    part_node_id: UUID
