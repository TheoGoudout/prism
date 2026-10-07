import uuid
from datetime import date as date_type
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, UniqueConstraint
from sqlalchemy.types import JSON
from sqlmodel import Field, Relationship, SQLModel

from app.models.common import timestamp_field
from app.models.integration import Platform, PlatformAccount


class ContentType(StrEnum):
    post = "post"
    reel = "reel"
    story = "story"
    video = "video"
    tweet = "tweet"
    article = "article"
    short = "short"
    email = "email"  # a newsletter / email campaign


# ---------------------------------------------------------------------------
# Shared metric fields
#
# Every platform maps its own metric names onto these normalised fields.
# A platform that doesn't report a metric leaves it as None.
#
# engagements is the same sum everywhere: likes + comments + shares + saves
# (see app.integrations.common.engagement_total). Clicks are counted apart.
# Google Analytics, which has no likes or shares, reports engaged sessions.
# Mailing platforms report each email campaign as a post: recipients are its
# impressions, unique opens its views and unique clicks its engagements (so the
# engagement rate is the click-to-open rate); a mailing list's subscribers are
# its followers.
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

    @property
    def exposures(self) -> int | None:
        """Views, or impressions where the platform only reports impressions."""
        return self.views if self.views is not None else self.impressions


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
    date: date_type

    # Calculated (stored for fast retrieval): engagements / views (see
    # app.crud.metrics.engagement_rate)
    engagement_rate: float | None = None

    # Platform-specific metrics that don't map onto the normalised fields
    raw_data: dict[str, Any] | None = Field(default=None, sa_type=JSON)

    created_at: datetime | None = timestamp_field(now=True)

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
    published_at: datetime = Field(sa_type=DateTime(timezone=True))
    engagement_rate: float | None = None

    raw_data: dict[str, Any] | None = Field(default=None, sa_type=JSON)

    # When a sync last saw the post's engagements grow enough (see
    # app.crud.metrics._track_engagement)
    # (its publication, until then), and its engagements at that time: they
    # decide how soon the integration is synced again.
    last_engaged_at: datetime | None = timestamp_field()
    engagements_at_last_engaged: int | None = None

    synced_at: datetime | None = timestamp_field(now=True)
    created_at: datetime | None = timestamp_field(now=True)

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
    platform: Platform
    published_at: datetime
    engagement_rate: float | None = None


class MetricTotals(SQLModel):
    """
    Aggregated metric totals over a date range. A metric none of the accounts
    reports is None, as opposed to 0 when it was reported as zero.
    """

    # Views, or impressions for accounts whose platform only reports
    # impressions: the cross-platform "times content was seen"
    exposures: int | None = None
    impressions: int | None = None
    reach: int | None = None
    views: int | None = None
    clicks: int | None = None
    engagements: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    saves: int | None = None
    followers_count: int | None = None  # latest snapshot value
    followers_gained: int | None = None
    # Net change of followers_count over the range: the latest count minus
    # the first one, for accounts with at least two counts in the range
    followers_growth: int | None = None
    # followers_growth / those accounts' first counts
    followers_growth_rate: float | None = None
    # engagements / exposures, over the accounts that report exposures
    engagement_rate: float | None = None


class MetricsSummary(SQLModel):
    """Overall and per-platform totals over a date range."""

    totals: MetricTotals
    by_platform: dict[str, MetricTotals]
    date_from: date_type
    date_to: date_type


class FollowersPoint(SQLModel):
    date: date_type
    followers: int


class PlatformFollowers(SQLModel):
    """
    A platform's follower count per day: the sum over its accounts of their
    latest count up to that day. Days before any count are left out.
    """

    platform: Platform
    points: list[FollowersPoint]


class TimeSeriesPoint(SQLModel):
    date: date_type
    exposures: int = 0
    impressions: int = 0
    reach: int = 0
    views: int = 0
    clicks: int = 0
    engagements: int = 0


class MetricBenchmark(SQLModel):
    """How a metric is distributed across a platform's post history."""

    sample_size: int
    p5: float  # the worst-performing 5% of posts fall below this
    p50: float
    p95: float  # the best-performing 5% of posts rise above this


class PostPerformance(PostPublic):
    """A recent post, situated within the platform's post history."""

    # Metric name → percentile rank (0–100) among the platform's posts; only
    # metrics that have a benchmark are ranked.
    percentile_ranks: dict[str, float]


class TopPostRanking(StrEnum):
    # The most engagements, whatever the account's audience
    engagements = "engagements"
    # The best posts relative to their own account's other posts
    account = "account"


class TopPost(PostPublic):
    account_name: str
    # Percentile rank (0–100) of the post's engagements among its account's
    # posts of the past year; None with too few posts to rank against
    account_percentile: float | None = None


class PostHistoryPoint(ContentMetrics):
    """A post's metrics only, for plotting the history over time."""

    id: uuid.UUID
    published_at: datetime
    engagement_rate: float | None = None


class PostPerformanceReport(SQLModel):
    """
    One account's latest posts, compared with its own post history: a popular
    account's posts and a small one's aren't comparable, even on one platform.
    """

    platform_account_id: uuid.UUID
    account_name: str
    platform: Platform
    history_from: date_type
    history_to: date_type
    history_size: int
    # Metric name → benchmark, for metrics reported on enough posts
    benchmarks: dict[str, MetricBenchmark]
    posts: list[PostPerformance]  # newest first
    history: list[PostHistoryPoint]  # oldest first
