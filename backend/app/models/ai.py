from datetime import datetime
from typing import Literal

from sqlmodel import Field, SQLModel

from app.models.common import get_datetime_utc


class Insight(SQLModel):
    title: str
    body: str
    type: Literal["positive", "negative", "neutral"]
    metric: str | None = None


class InsightsResponse(SQLModel):
    insights: list[Insight]
    generated_at: datetime = Field(default_factory=get_datetime_utc)


class ReportResponse(SQLModel):
    report: str  # markdown
    generated_at: datetime = Field(default_factory=get_datetime_utc)
