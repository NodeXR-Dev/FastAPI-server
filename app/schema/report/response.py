from uuid import UUID

from pydantic import BaseModel, Field


class ParticipantRatioResponse(BaseModel):
    user_id: UUID
    nickname: str
    ratio: float = Field(ge=0.0, le=100.0)


class ReportResponse(BaseModel):
    topic: str
    participants: list[str]
    participants_ratio: list[ParticipantRatioResponse]
    final_2D_image: str | None
