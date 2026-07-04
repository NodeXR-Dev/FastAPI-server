from uuid import UUID

from pydantic import BaseModel, Field

class Connection2D(BaseModel):
    part_node_id: UUID
    node_id: UUID
    
class Generate2DRequest(BaseModel):
    room_id: UUID
    connections: list[Connection2D] = Field(default_factory=list)

class Generate3DRequest(BaseModel):
    room_id: UUID
    asset_id: UUID | None = None