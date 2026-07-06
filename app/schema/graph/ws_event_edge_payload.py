from uuid import UUID
from pydantic import BaseModel


class EdgeCreatePayload(BaseModel):
    job_id: UUID
    from_node_id: UUID
    to_node_id: UUID

class EdgeDeletePayload(BaseModel):
    edge_id: UUID