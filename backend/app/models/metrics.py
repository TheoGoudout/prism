import uuid
from datetime import date as date_type
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import Column, Date, UniqueConstraint
from sqlalchemy import DateTime as SADateTime
from sqlalchemy.types import JSON
from sqlmodel import Field, Relationship, SQLModel

from app.models.common import get_datetime_utc
from app.models.integration import PlatformAccount


class ContentType(str, Enum):
    post = "post"
    reel = "reel"
    story = "story"
    video = "video"
    tweet = "tweet"
    article = "article"
    short = "short"


# ---------------------------------------------------------------------------
# Shared metric fields
#
# Every platform maps its own metric names onto these normalised fields.
# A platform that doesn't report a metric leaves it as None.
# ---------------------------------------------------------------------------


class ContentMetrics(SQLModel):
    """Reach and engagement metrics, reported per post and per day."""

    impressions: int | None = None
    reach: int | None = None
    views: int | None = None
    engagements: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    clicks: int | None = None
    saves: int | None = None


class AccountMetrics(ContentMetrics):
    """Content metrics plus account-level audience figures, reported per day."""

    followers_count: int | None = None
    followers_gained: int | None = None
    followers_lost: int | None = None
    posts_count: int | None = None


# ---------------------------------------------------------------------------
# MetricSnapshot — one row per (platform_account, date)
# ---------------------------------------------------------------------------


class MetricSnapshot(AccountMetrics, table=True):
    """
    Daily aggregate metrics for a platform account.
    Weekly / monthly views are computed on-the-fly by summing over date
    ranges — no separate rollup tables needed.
    """

    __tablename__ = "metricsnapshot"
    __table_args__ = (
        UniqueConstraint(
            "platform_account_id", "date", name="uq_metricsnapshot_account_date"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    platform_account_id: uuid.UUID = Field(
        foreign_key="platformaccount.id", nullable=False, ondelete="CASCADE", index=True
    )
    date: date_type = Field(sa_column=Column(Date, nullable=False))

    # Calculated (stored for fast retrieval): engagements / reach
    engagement_rate: float | None = None

    # Platform-specific metrics that don't map onto the normalised fields
    raw_data: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )

    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(SADateTime(timezone=True), nullable=True),
    )

    platform_account: PlatformAccount | None = Relationship(
        back_populates="metric_snapshots"
    )


# ---------------------------------------------------------------------------
# Post — one row per published post / reel / story / tweet / etc.
# ---------------------------------------------------------------------------


class PostContent(SQLModel):
    """What was published (as opposed to how it performed)."""

    external_id: str = Field(max_length=255)
    content_type: ContentType
    text: str | None = None
    media_url: str | None = Field(default=None, max_length=2048)
    permalink: str | None = Field(default=None, max_length=2048)


class Post(PostContent, ContentMetrics, table=True):
    """Per-post metrics synced from each platform."""

    __table_args__ = (
        UniqueConstraint(
            "platform_account_id", "external_id", name="uq_post_account_external_id"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    platform_account_id: uuid.UUID = Field(
        foreign_key="platformaccount.id", nullable=False, ondelete="CASCADE", index=True
    )
    published_at: datetime = Field(
        sa_column=Column(SADateTime(timezone=True), nullable=False)
    )
    engagement_rate: float | None = None

    raw_data: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )

    synced_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(SADateTime(timezone=True), nullable=True),
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(SADateTime(timezone=True), nullable=True),
    )

    platform_account: PlatformAccount | None = Relationship(back_populates="posts")


# ---------------------------------------------------------------------------
# Sync inputs — used internally by sync tasks, not exposed via the API
# ---------------------------------------------------------------------------


class MetricSnapshotUpsert(AccountMetrics):
    date: date_type
    raw_data: dict[str, Any] | None = None


class PostUpsert(PostContent, ContentMetrics):
    published_at: datetime
    raw_data: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# API responses
# ---------------------------------------------------------------------------


class PostPublic(PostContent, ContentMetrics):
    id: uuid.UUID
    platform_account_id: uuid.UUID
    published_at: datetime
    engagement_rate: float | None = None


class PostsPublic(SQLModel):
    data: list[PostPublic]
    count: int


class MetricTotals(SQLModel):
    """Aggregated metric totals over a date range."""

    impressions: int = 0
    reach: int = 0
    views: int = 0
    clicks: int = 0
    engagements: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    followers_count: int | None = None  # latest snapshot value
    followers_gained: int = 0


class MetricsSummary(SQLModel):
    """Response for GET /metrics/summary."""

    totals: MetricTotals
    by_platform: dict[str, MetricTotals]
    date_from: date_type
    date_to: date_type


class TimeSeriesPoint(SQLModel):
    date: date_type
    impressions: int = 0
    reach: int = 0
    views: int = 0
    clicks: int = 0
    engagements: int = 0


class MetricsTimeSeries(SQLModel):
    """Response for GET /metrics/timeseries."""

    data: list[TimeSeriesPoint]
