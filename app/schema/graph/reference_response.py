from uuid import UUID

from pydantic import BaseModel


class GenerateReferenceResponse(BaseModel):
    room_id: UUID
    node_id: UUID
    reference_url: str
