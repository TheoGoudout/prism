"""
Metrics API — dashboard data for a workspace.

Every endpoint takes the same filters: an optional `platform`, and an optional
`date_from` / `date_to` range that defaults to the last 30 days.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import MetricsQueryDep, SessionDep
from app.models.metrics import (
    MetricsSummary,
    PlatformFollowers,
    PostPublic,
    TimeSeriesPoint,
)
from app.services import metrics as metrics_service

router = APIRouter(prefix="/workspaces/{workspace_id}/metrics", tags=["metrics"])


@router.get("/summary", response_model=MetricsSummary)
def get_summary(session: SessionDep, query: MetricsQueryDep) -> Any:
    """Overall and per-platform KPI totals over the date range."""
    return metrics_service.summarize(session, query)


@router.get("/timeseries", response_model=list[TimeSeriesPoint])
def get_timeseries(session: SessionDep, query: MetricsQueryDep) -> Any:
    """One data point per calendar day in the range, for charts."""
    return metrics_service.timeseries(session, query)


@router.get("/followers", response_model=list[PlatformFollowers])
def get_followers(session: SessionDep, query: MetricsQueryDep) -> Any:
    """Each platform's follower count per day, for growth charts."""
    return metrics_service.followers_timeseries(session, query)


@router.get("/posts", response_model=list[PostPublic])
def get_top_posts(
    session: SessionDep,
    query: MetricsQueryDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> Any:
    """Top-performing posts (by engagements) published in the date range."""
    return metrics_service.top_posts(session, query, limit)
