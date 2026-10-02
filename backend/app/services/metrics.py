"""
Workspace-level metrics: what the dashboards and the AI endpoints show.

Every function aggregates the daily snapshots / posts of a workspace's active
platform accounts, optionally restricted to one platform.
"""

import math
import uuid
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from sqlmodel import Session

from app import crud
from app.models.integration import Platform
from app.models.metrics import (
    MetricBenchmark,
    MetricSnapshot,
    MetricsSummary,
    MetricTotals,
    Post,
    PostHistoryPoint,
    PostPerformance,
    PostPerformanceReport,
    PostPublic,
    TimeSeriesPoint,
)

DEFAULT_RANGE_DAYS = 30

# Fields summed across days and accounts. followers_count is a level, not a
# flow, so it is handled separately (latest value per account).
SUMMED_FIELDS = (
    "impressions",
    "reach",
    "views",
    "clicks",
    "engagements",
    "likes",
    "comments",
    "shares",
    "saves",
    "followers_gained",
)
CHART_FIELDS = ("impressions", "reach", "views", "clicks", "engagements")

# Post metrics that posts are ranked on (engagement_rate = engagements / reach)
POST_PERFORMANCE_FIELDS = (
    "impressions",
    "reach",
    "views",
    "engagements",
    "engagement_rate",
    "likes",
    "comments",
    "shares",
    "clicks",
    "saves",
)
DEFAULT_POST_HISTORY_DAYS = 365
# Below this many posts, percentiles say little, so a metric gets no benchmark
MIN_BENCHMARK_SAMPLE = 5


@dataclass(frozen=True)
class MetricsQuery:
    """Which metrics to aggregate: a workspace, optionally one platform, a range."""

    workspace_id: uuid.UUID
    platform: Platform | None
    date_from: date
    date_to: date

    @classmethod
    def build(
        cls,
        workspace_id: uuid.UUID,
        platform: Platform | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> MetricsQuery:
        """Missing bounds default to the last 30 days."""
        date_to = date_to or date.today()
        date_from = date_from or date_to - timedelta(days=DEFAULT_RANGE_DAYS - 1)
        return cls(workspace_id, platform, date_from, date_to)


def _account_platforms(session: Session, query: MetricsQuery) -> dict[uuid.UUID, str]:
    """{account id: platform name} for the workspace's active accounts."""
    accounts = crud.get_accounts_for_workspace(
        session=session, workspace_id=query.workspace_id, platform=query.platform
    )
    return {a.id: a.platform.value for a in accounts}


def _snapshots(
    session: Session, query: MetricsQuery, account_ids: Sequence[uuid.UUID]
) -> Sequence[MetricSnapshot]:
    return crud.get_snapshots_for_accounts(
        session=session,
        platform_account_ids=account_ids,
        start_date=query.date_from,
        end_date=query.date_to,
    )


def summarize(session: Session, query: MetricsQuery) -> MetricsSummary:
    """Overall and per-platform totals over the range."""
    account_platform = _account_platforms(session, query)
    snapshots = _snapshots(session, query, list(account_platform))

    totals: dict[str, int] = defaultdict(int)
    by_platform: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    # Snapshots are ordered by date, so the last one seen per account wins
    latest_followers: dict[uuid.UUID, int] = {}

    for snap in snapshots:
        plat = account_platform[snap.platform_account_id]
        for field in SUMMED_FIELDS:
            value = getattr(snap, field) or 0
            totals[field] += value
            by_platform[plat][field] += value
        if snap.followers_count is not None:
            latest_followers[snap.platform_account_id] = snap.followers_count

    platform_followers: dict[str, int] = defaultdict(int)
    for account_id, followers in latest_followers.items():
        platform_followers[account_platform[account_id]] += followers

    return MetricsSummary(
        totals=MetricTotals(
            **totals,
            followers_count=sum(latest_followers.values())
            if latest_followers
            else None,
        ),
        by_platform={
            plat: MetricTotals(**sums, followers_count=platform_followers.get(plat))
            for plat, sums in by_platform.items()
        },
        date_from=query.date_from,
        date_to=query.date_to,
    )


def timeseries(session: Session, query: MetricsQuery) -> list[TimeSeriesPoint]:
    """One point per calendar day in the range (zeros for days without data)."""
    account_platform = _account_platforms(session, query)
    if not account_platform:
        return []
    snapshots = _snapshots(session, query, list(account_platform))

    by_date: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for snap in snapshots:
        for field in CHART_FIELDS:
            by_date[snap.date][field] += getattr(snap, field) or 0

    days = (query.date_to - query.date_from).days + 1
    return [
        TimeSeriesPoint(date=day, **by_date.get(day, {}))
        for day in (query.date_from + timedelta(days=i) for i in range(days))
    ]


def top_posts(session: Session, query: MetricsQuery, limit: int = 10) -> Sequence[Post]:
    """The workspace's most-engaging posts published in the range."""
    return crud.get_top_posts(
        session=session,
        platform_account_ids=list(_account_platforms(session, query)),
        start_date=query.date_from,
        end_date=query.date_to,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Post performance
# ---------------------------------------------------------------------------


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """The q-th percentile (0–100), interpolating linearly between values."""
    position = (len(sorted_values) - 1) * q / 100
    lower = math.floor(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _percentile_rank(sorted_values: Sequence[float], value: float) -> float:
    """Share of the values below ``value`` (ties count half), from 0 to 100."""
    below = bisect_left(sorted_values, value)
    ties = bisect_right(sorted_values, value) - below
    return round(100 * (below + ties / 2) / len(sorted_values), 1)


def _performance_report(
    platform: Platform,
    history: Sequence[Post],
    *,
    history_from: date,
    history_to: date,
    limit: int,
) -> PostPerformanceReport:
    """Rank the newest ``limit`` posts against the whole history, per metric."""
    distributions: dict[str, list[float]] = {}
    benchmarks: dict[str, MetricBenchmark] = {}
    for field in POST_PERFORMANCE_FIELDS:
        values = sorted(
            v for v in (getattr(post, field) for post in history) if v is not None
        )
        if len(values) < MIN_BENCHMARK_SAMPLE:
            continue
        distributions[field] = values
        benchmarks[field] = MetricBenchmark(
            sample_size=len(values),
            p5=_percentile(values, 5),
            p50=_percentile(values, 50),
            p95=_percentile(values, 95),
        )

    posts = [
        PostPerformance(
            **PostPublic.model_validate(post).model_dump(),
            percentile_ranks={
                field: _percentile_rank(values, value)
                for field, values in distributions.items()
                if (value := getattr(post, field)) is not None
            },
        )
        for post in history[:limit]
    ]
    return PostPerformanceReport(
        platform=platform,
        history_from=history_from,
        history_to=history_to,
        history_size=len(history),
        benchmarks=benchmarks,
        posts=posts,
        history=[PostHistoryPoint.model_validate(post) for post in reversed(history)],
    )


def post_performance(
    session: Session,
    workspace_id: uuid.UUID,
    platform: Platform | None = None,
    limit: int = 20,
    history_days: int = DEFAULT_POST_HISTORY_DAYS,
) -> list[PostPerformanceReport]:
    """
    Per platform that has posts: the latest posts, with each metric situated
    between the worst (P5) and best (P95) posts of the last ``history_days``.
    Platforms are benchmarked separately since their audiences and metrics
    aren't comparable.
    """
    accounts = crud.get_accounts_for_workspace(
        session=session, workspace_id=workspace_id, platform=platform
    )
    history_to = date.today()
    history_from = history_to - timedelta(days=history_days - 1)
    account_platform = {a.id: a.platform for a in accounts}
    posts = crud.get_posts_for_accounts(
        session=session,
        platform_account_ids=list(account_platform),
        start_date=history_from,
    )

    by_platform: dict[Platform, list[Post]] = defaultdict(list)
    for post in posts:  # newest first, which each platform's list keeps
        by_platform[account_platform[post.platform_account_id]].append(post)

    return [
        _performance_report(
            plat,
            by_platform[plat],
            history_from=history_from,
            history_to=history_to,
            limit=limit,
        )
        for plat in Platform
        if plat in by_platform
    ]
