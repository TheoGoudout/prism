import uuid
from datetime import date as date_type
from datetime import datetime
from typing import Literal

from sqlmodel import SQLModel

from app.models.common import get_datetime_utc
from app.models.integration import Platform


class AIRequest(SQLModel):
    """Common fields for AI generation requests."""

    workspace_id: uuid.UUID
    platform: Platform | None = None
    date_from: date_type | None = None
    date_to: date_type | None = None


class Insight(SQLModel):
    title: str
    body: str
    type: Literal["positive", "negative", "neutral"]
    metric: str | None = None


class InsightsResponse(SQLModel):
    insights: list[Insight]
    generated_at: datetime = None  # type: ignore[assignment]

    def model_post_init(self, __context: object) -> None:
        if self.generated_at is None:
            self.generated_at = get_datetime_utc()


class ReportResponse(SQLModel):
    report: str  # markdown
    generated_at: datetime = None  # type: ignore[assignment]

    def model_post_init(self, __context: object) -> None:
        if self.generated_at is None:
            self.generated_at = get_datetime_utc()
