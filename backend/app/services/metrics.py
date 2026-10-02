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
    PostPublic,
    TimeSeriesPoint,
)

DEFAULT_RANGE_DAYS = 30

# Reach and engagement fields, reported by daily snapshots and by posts
CONTENT_FIELDS = (
    "impressions",
    "reach",
    "views",
    "clicks",
    "engagements",
    "likes",
    "comments",
    "shares",
    "saves",
)
# Fields summed across days and accounts. followers_count is a level, not a
# flow, so it is handled separately (latest value per account).
SUMMED_FIELDS = (*CONTENT_FIELDS, "followers_gained")
CHART_FIELDS = ("exposures", "impressions", "reach", "views", "clicks", "engagements")

# {account id: {day: {field: value}}}, only the fields known for that day
DailyMetrics = dict[uuid.UUID, dict[date, dict[str, int]]]


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


def _daily_metrics(
    snapshots: Sequence[MetricSnapshot], posts: Sequence[Post]
) -> DailyMetrics:
    """
    Each account's metrics per day, so that every platform contributes to the
    same totals and charts:

    - a field the account's daily snapshots report comes from the snapshots;
    - any other content field comes from the account's posts, counted on the
      day they were published. Twitter, LinkedIn and TikTok only report
      engagement per post, and Instagram has no daily views or engagements.
    - exposures are the account's views, or its impressions if it reports
      no views, so platforms that only count impressions are comparable.

    The choice is made per account and field over the whole range, so one
    series never mixes the two sources.
    """
    daily: DailyMetrics = defaultdict(lambda: defaultdict(dict))
    from_snapshots: dict[uuid.UUID, set[str]] = defaultdict(set)

    for snap in snapshots:
        day = daily[snap.platform_account_id][snap.date]
        for field in SUMMED_FIELDS:
            value = getattr(snap, field)
            if value is not None:
                day[field] = value
                from_snapshots[snap.platform_account_id].add(field)

    for post in posts:
        day = daily[post.platform_account_id][post.published_at.date()]
        for field in CONTENT_FIELDS:
            value = getattr(post, field)
            if (
                value is not None
                and field not in from_snapshots[post.platform_account_id]
            ):
                day[field] = day.get(field, 0) + value

    for days in daily.values():
        source = (
            "views" if any("views" in day for day in days.values()) else "impressions"
        )
        for day in days.values():
            if source in day:
                day["exposures"] = day[source]
    return daily


def _load_daily_metrics(
    session: Session, query: MetricsQuery, account_ids: Sequence[uuid.UUID]
) -> tuple[Sequence[MetricSnapshot], DailyMetrics]:
    snapshots = _snapshots(session, query, account_ids)
    posts = crud.get_posts_for_accounts(
        session=session,
        platform_account_ids=account_ids,
        start_date=query.date_from,
        end_date=query.date_to,
    )
    return snapshots, _daily_metrics(snapshots, posts)


def _totals(
    account_sums: Sequence[dict[str, int]], followers: Sequence[int]
) -> MetricTotals:
    """
    Totals of several accounts. The engagement rate only counts the
    engagements of accounts that report exposures, so that its numerator and
    denominator cover the same accounts.
    """
    sums: dict[str, int] = defaultdict(int)
    rated_engagements = 0
    for account in account_sums:
        for field, value in account.items():
            sums[field] += value
        if account.get("exposures"):
            rated_engagements += account.get("engagements", 0)

    exposures = sums.get("exposures")
    return MetricTotals(
        **sums,
        followers_count=sum(followers) if followers else None,
        engagement_rate=round(rated_engagements / exposures, 6) if exposures else None,
    )


def summarize(session: Session, query: MetricsQuery) -> MetricsSummary:
    """Overall and per-platform totals over the range."""
    account_platform = _account_platforms(session, query)
    snapshots, daily = _load_daily_metrics(session, query, list(account_platform))

    account_sums: dict[uuid.UUID, dict[str, int]] = {}
    for account_id, days in daily.items():
        sums: dict[str, int] = defaultdict(int)
        for day in days.values():
            for field, value in day.items():
                sums[field] += value
        account_sums[account_id] = sums

    # Snapshots are ordered by date, so the last one seen per account wins
    latest_followers: dict[uuid.UUID, int] = {}
    for snap in snapshots:
        if snap.followers_count is not None:
            latest_followers[snap.platform_account_id] = snap.followers_count

    platform_accounts: dict[str, list[uuid.UUID]] = defaultdict(list)
    for account_id in account_sums:
        platform_accounts[account_platform[account_id]].append(account_id)

    def totals_of(account_ids: Sequence[uuid.UUID]) -> MetricTotals:
        return _totals(
            [account_sums[a] for a in account_ids],
            [latest_followers[a] for a in account_ids if a in latest_followers],
        )

    return MetricsSummary(
        totals=totals_of(list(account_sums)),
        by_platform={plat: totals_of(ids) for plat, ids in platform_accounts.items()},
        date_from=query.date_from,
        date_to=query.date_to,
    )


def timeseries(session: Session, query: MetricsQuery) -> list[TimeSeriesPoint]:
    """One point per calendar day in the range (zeros for days without data)."""
    account_platform = _account_platforms(session, query)
    if not account_platform:
        return []
    _, daily = _load_daily_metrics(session, query, list(account_platform))

    by_date: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for account_days in daily.values():
        for day, values in account_days.items():
            for field in CHART_FIELDS:
                by_date[day][field] += values.get(field, 0)

    days = (query.date_to - query.date_from).days + 1
    return [
        TimeSeriesPoint(date=day, **by_date.get(day, {}))
        for day in (query.date_from + timedelta(days=i) for i in range(days))
    ]


def top_posts(
    session: Session, query: MetricsQuery, limit: int = 10
) -> list[PostPublic]:
    """The workspace's most-engaging posts published in the range."""
    account_platform = _account_platforms(session, query)
    posts = crud.get_top_posts(
        session=session,
        platform_account_ids=list(account_platform),
        start_date=query.date_from,
        end_date=query.date_to,
        limit=limit,
    )
    return [
        PostPublic.model_validate(
            post, update={"platform": account_platform[post.platform_account_id]}
        )
        for post in posts
    ]
