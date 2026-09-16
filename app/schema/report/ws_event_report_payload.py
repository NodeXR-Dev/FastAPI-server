from uuid import UUID

from pydantic import BaseModel


class ReportGeneratedPayload(BaseModel):
    report_id: UUID
    report_version: int
    report_url: str
