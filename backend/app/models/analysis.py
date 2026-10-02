"""
AI performance analyses: a full LLM review of a workspace's posts and metrics
over a period, run on demand or on a schedule and optionally emailed.
"""

import uuid
from datetime import date as date_type
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import EmailStr, field_validator, model_validator
from sqlalchemy import Column, Date
from sqlalchemy import DateTime as SADateTime
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel

from app.models.common import get_datetime_utc

MAX_RECIPIENTS = 20


class AnalysisStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class AnalysisTrigger(StrEnum):
    manual = "manual"
    scheduled = "scheduled"


class AnalysisKind(StrEnum):
    standard = "standard"
    # A year in review: more posts and a month-by-month breakdown, so a
    # costlier LLM call. Only run on demand, never scheduled.
    yearly = "yearly"


class AnalysisFrequency(StrEnum):
    weekly = "weekly"
    biweekly = "biweekly"  # every two weeks
    monthly = "monthly"


Verdict = Literal["strong", "average", "weak"]


# ---------------------------------------------------------------------------
# Analysis result — the structured output of the LLM, stored as JSON
# ---------------------------------------------------------------------------


class Finding(SQLModel):
    """Something that worked, or didn't."""

    title: str
    detail: str


class Recommendation(SQLModel):
    title: str
    detail: str
    priority: Literal["high", "medium", "low"] = "medium"


class PlatformAnalysis(SQLModel):
    platform: str
    verdict: Verdict
    summary: str


class TopicAnalysis(SQLModel):
    """Posts grouped by what they are about."""

    name: str
    verdict: Verdict
    summary: str
    post_ids: list[uuid.UUID] = []


class PostAnalysis(SQLModel):
    post_id: uuid.UUID
    verdict: Verdict
    analysis: str
    suggestion: str | None = None
    topic: str | None = None


class PeriodAnalysis(SQLModel):
    """One month of a yearly analysis."""

    label: str  # e.g. "2026-03"
    verdict: Verdict
    summary: str


class AnalysisResult(SQLModel):
    summary: str
    what_worked: list[Finding] = []
    what_didnt_work: list[Finding] = []
    recommendations: list[Recommendation] = []
    platforms: list[PlatformAnalysis] = []
    topics: list[TopicAnalysis] = []
    posts: list[PostAnalysis] = []
    periods: list[PeriodAnalysis] = []  # yearly analyses only


# ---------------------------------------------------------------------------
# Database models
# ---------------------------------------------------------------------------


class PerformanceAnalysis(SQLModel, table=True):
    __tablename__ = "performanceanalysis"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspace.id", nullable=False, ondelete="CASCADE", index=True
    )
    date_from: date_type = Field(sa_column=Column(Date, nullable=False))
    date_to: date_type = Field(sa_column=Column(Date, nullable=False))
    trigger: AnalysisTrigger = Field(default=AnalysisTrigger.manual)
    kind: AnalysisKind = Field(default=AnalysisKind.standard)
    status: AnalysisStatus = Field(default=AnalysisStatus.pending)
    error: str | None = Field(default=None, max_length=1024)
    # An AnalysisResult once completed
    result: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    post_count: int = 0
    # Who receives the analysis by email once it completes
    email_recipients: list[str] = Field(default=[], sa_type=JSON)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(SADateTime(timezone=True), nullable=True),
    )
    completed_at: datetime | None = Field(
        default=None, sa_column=Column(SADateTime(timezone=True), nullable=True)
    )
    emailed_at: datetime | None = Field(
        default=None, sa_column=Column(SADateTime(timezone=True), nullable=True)
    )


class ScheduleSettings(SQLModel):
    """When a workspace's analysis runs, and who receives it by email."""

    enabled: bool = False
    frequency: AnalysisFrequency = AnalysisFrequency.weekly
    # Weekly and biweekly runs: 0 = Monday … 6 = Sunday
    weekday: int = Field(default=0, ge=0, le=6)
    # Monthly runs; capped at 28 so every month has the day
    day_of_month: int = Field(default=1, ge=1, le=28)
    hour: int = Field(default=8, ge=0, le=23)
    timezone: str = Field(default="UTC", max_length=64)
    email_enabled: bool = False
    email_recipients: list[EmailStr] = Field(
        default=[], max_length=MAX_RECIPIENTS, sa_type=JSON
    )

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError, ValueError:
            raise ValueError(f"Unknown time zone: {value}")
        return value


class AnalysisSchedule(ScheduleSettings, table=True):
    """At most one per workspace."""

    __tablename__ = "analysisschedule"

    workspace_id: uuid.UUID = Field(
        foreign_key="workspace.id", primary_key=True, ondelete="CASCADE"
    )
    next_run_at: datetime | None = Field(
        default=None, sa_column=Column(SADateTime(timezone=True), nullable=True)
    )
    last_run_at: datetime | None = Field(
        default=None, sa_column=Column(SADateTime(timezone=True), nullable=True)
    )


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class AnalysisCreate(SQLModel):
    """
    The period to analyze; defaults to the last 7 days, or the last 12 months
    for a yearly analysis.
    """

    kind: AnalysisKind = AnalysisKind.standard
    date_from: date_type | None = None
    date_to: date_type | None = None
    email_recipients: list[EmailStr] = Field(default=[], max_length=MAX_RECIPIENTS)

    @model_validator(mode="after")
    def _ordered(self) -> AnalysisCreate:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class AnalysisSummaryPublic(SQLModel):
    """An analysis without its (large) result, for history lists."""

    id: uuid.UUID
    date_from: date_type
    date_to: date_type
    trigger: AnalysisTrigger
    kind: AnalysisKind
    status: AnalysisStatus
    error: str | None = None
    post_count: int
    created_at: datetime | None = None
    completed_at: datetime | None = None
    emailed_at: datetime | None = None


class AnalysesPublic(SQLModel):
    data: list[AnalysisSummaryPublic]
    count: int


class AnalyzedPost(SQLModel):
    """What the UI needs to show a post next to its analysis."""

    id: uuid.UUID
    platform: str
    content_type: str
    text: str | None = None
    permalink: str | None = None
    published_at: datetime
    impressions: int | None = None
    reach: int | None = None
    views: int | None = None
    engagements: int | None = None
    engagement_rate: float | None = None


class AnalysisPublic(AnalysisSummaryPublic):
    email_recipients: list[str] = []
    result: AnalysisResult | None = None
    posts: list[AnalyzedPost] = []


class SchedulePublic(ScheduleSettings):
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
