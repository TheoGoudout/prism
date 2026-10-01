"""
Metrics API — dashboard data endpoints.

All endpoints require workspace membership. The caller identifies the workspace
via the `workspace_id` query parameter, and optionally narrows results to a
single platform via `platform`.
"""

import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.models.integration import Platform
from app.models.metrics import (
    MetricsSummary,
    MetricsTimeSeries,
    PostPublic,
    PostsPublic,
    TimeSeriesPoint,
)
from app.services import metrics as metrics_service

router = APIRouter(prefix="/metrics", tags=["metrics"])

_DEFAULT_DAYS = 30


def _default_date_range() -> tuple[date, date]:
    end = date.today()
    start = end - timedelta(days=_DEFAULT_DAYS - 1)
    return start, end


def _require_member(session: Any, workspace_id: uuid.UUID, current_user: Any) -> None:
    member = crud.get_member(
        session=session, workspace_id=workspace_id, user_id=current_user.id
    )
    if not member:
        raise HTTPException(status_code=404, detail="Workspace not found")


def _account_ids_for_workspace(
    session: Any,
    workspace_id: uuid.UUID,
    platform: Platform | None,
) -> list[uuid.UUID]:
    """Return platform account IDs scoped to a workspace (and optional platform)."""
    accounts = crud.get_accounts_for_workspace(
        session=session, workspace_id=workspace_id, platform=platform
    )
    return [a.id for a in accounts]


# ---------------------------------------------------------------------------
# Summary — KPI cards
# ---------------------------------------------------------------------------


@router.get("/summary", response_model=MetricsSummary)
def get_summary(
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    platform: Platform | None = None,
    date_from: date = Query(default_factory=lambda: _default_date_range()[0]),
    date_to: date = Query(default_factory=lambda: _default_date_range()[1]),
) -> Any:
    """
    Aggregate KPI totals for a workspace over a date range.
    Returns overall totals and a per-platform breakdown.
    """
    _require_member(session, workspace_id, current_user)
    return metrics_service.summarize(
        session=session,
        workspace_id=workspace_id,
        platform=platform,
        date_from=date_from,
        date_to=date_to,
    )


# ---------------------------------------------------------------------------
# Timeseries — chart data
# ---------------------------------------------------------------------------


@router.get("/timeseries", response_model=MetricsTimeSeries)
def get_timeseries(
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    platform: Platform | None = None,
    date_from: date = Query(default_factory=lambda: _default_date_range()[0]),
    date_to: date = Query(default_factory=lambda: _default_date_range()[1]),
) -> Any:
    """
    Per-day aggregated metrics for line/bar charts.
    Returns one data point per calendar day in the requested range.
    """
    _require_member(session, workspace_id, current_user)

    account_ids = _account_ids_for_workspace(session, workspace_id, platform)
    if not account_ids:
        return MetricsTimeSeries(data=[])

    snapshots = crud.get_snapshots_for_accounts(
        session=session,
        platform_account_ids=account_ids,
        start_date=date_from,
        end_date=date_to,
    )

    # Aggregate by date
    by_date: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    _CHART_FIELDS = ("impressions", "reach", "views", "clicks", "engagements")
    for snap in snapshots:
        for field in _CHART_FIELDS:
            by_date[snap.date][field] += getattr(snap, field) or 0

    # Fill every day in range (even days with no data → zeros)
    data: list[TimeSeriesPoint] = []
    current = date_from
    while current <= date_to:
        d = by_date.get(current, {})
        data.append(
            TimeSeriesPoint(
                date=current,
                impressions=d.get("impressions", 0),
                reach=d.get("reach", 0),
                views=d.get("views", 0),
                clicks=d.get("clicks", 0),
                engagements=d.get("engagements", 0),
            )
        )
        current += timedelta(days=1)

    return MetricsTimeSeries(data=data)


# ---------------------------------------------------------------------------
# Top posts
# ---------------------------------------------------------------------------


@router.get("/posts", response_model=PostsPublic)
def get_top_posts(
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    platform: Platform | None = None,
    date_from: date = Query(default_factory=lambda: _default_date_range()[0]),
    date_to: date = Query(default_factory=lambda: _default_date_range()[1]),
    limit: int = Query(default=10, ge=1, le=50),
) -> Any:
    """
    Top-performing posts (by engagements) for a workspace over a date range.
    """
    _require_member(session, workspace_id, current_user)

    account_ids = _account_ids_for_workspace(session, workspace_id, platform)
    if not account_ids:
        return PostsPublic(data=[], count=0)

    posts = crud.get_top_posts(
        session=session,
        platform_account_ids=account_ids,
        start_date=date_from,
        end_date=date_to,
        limit=limit,
    )
    return PostsPublic(
        data=[PostPublic.model_validate(p) for p in posts], count=len(posts)
    )
