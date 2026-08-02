from uuid import UUID

from pydantic import BaseModel, Field

class Connection2D(BaseModel):
    part_node_id: UUID
    node_id: UUID
    
class Generate2DGraphRequest(BaseModel):
    room_id: UUID
    user_id: UUID
    job_id: UUID
    connections: list[Connection2D] = Field(default_factory=list)
    
class Generate2DFeatureRequest(BaseModel):
    room_id: UUID
    user_id: UUID
    job_id: UUID

class Generate3DRequest(BaseModel):
    room_id: UUID
    user_id: UUID
    job_id: UUID
    asset_id: UUID | None = None
