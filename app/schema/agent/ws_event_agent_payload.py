from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentGuidePayload(BaseModel):
    guide_id: UUID = Field(default_factory=uuid4)
    guide_type: str
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)
