"""
Workspace-level metrics: what the dashboards and the AI endpoints show.

Every function aggregates the daily snapshots / posts of a workspace's active
platform accounts, optionally restricted to one platform.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from sqlmodel import Session

from app import crud
from app.models.integration import Platform
from app.models.metrics import (
    MetricSnapshot,
    MetricsSummary,
    MetricTotals,
    Post,
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
    ) -> "MetricsQuery":
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
