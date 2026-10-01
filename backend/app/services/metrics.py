"""
Metrics aggregation shared by the dashboard API and the AI endpoints.
"""
import uuid
from collections import defaultdict
from datetime import date

from sqlmodel import Session

from app import crud
from app.models.integration import Platform
from app.models.metrics import MetricsSummary, MetricTotals

# Fields summed across days and accounts. followers_count is a level, not a
# flow, so it is handled separately (latest value per account).
SUM_FIELDS = (
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


def summarize(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    platform: Platform | None,
    date_from: date,
    date_to: date,
) -> MetricsSummary:
    """Aggregate daily snapshots into overall and per-platform totals."""
    accounts = crud.get_accounts_for_workspace(
        session=session, workspace_id=workspace_id, platform=platform
    )
    account_platform = {a.id: a.platform.value for a in accounts}
    if not account_platform:
        return MetricsSummary(
            totals=MetricTotals(), by_platform={}, date_from=date_from, date_to=date_to
        )

    snapshots = crud.get_snapshots_for_accounts(
        session=session,
        platform_account_ids=list(account_platform),
        start_date=date_from,
        end_date=date_to,
    )

    totals: dict[str, int] = defaultdict(int)
    by_platform: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    # Snapshots are ordered by date, so the last one seen per account wins
    latest_followers: dict[uuid.UUID, int] = {}

    for snap in snapshots:
        plat = account_platform.get(snap.platform_account_id, "unknown")
        for field in SUM_FIELDS:
            val = getattr(snap, field) or 0
            totals[field] += val
            by_platform[plat][field] += val
        if snap.followers_count is not None:
            latest_followers[snap.platform_account_id] = snap.followers_count

    plat_followers: dict[str, int] = defaultdict(int)
    for acc_id, followers in latest_followers.items():
        plat_followers[account_platform.get(acc_id, "unknown")] += followers

    return MetricsSummary(
        totals=MetricTotals(
            **totals,
            followers_count=sum(latest_followers.values()) if latest_followers else None,
        ),
        by_platform={
            plat: MetricTotals(**d, followers_count=plat_followers.get(plat))
            for plat, d in by_platform.items()
        },
        date_from=date_from,
        date_to=date_to,
    )
