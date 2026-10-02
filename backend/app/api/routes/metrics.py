"""
Metrics API — dashboard data for a workspace.

Every endpoint takes the same filters: an optional `platform`, and an optional
`date_from` / `date_to` range that defaults to the last 30 days — except
/posts/performance, which looks back over a longer post history.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import CurrentMember, MetricsQueryDep, SessionDep
from app.models.integration import Platform
from app.models.metrics import (
    MetricsSummary,
    PostPerformanceReport,
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


@router.get("/posts", response_model=list[PostPublic])
def get_top_posts(
    session: SessionDep,
    query: MetricsQueryDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> Any:
    """Top-performing posts (by engagements) published in the date range."""
    return metrics_service.top_posts(session, query, limit)


@router.get("/posts/performance", response_model=list[PostPerformanceReport])
def get_post_performance(
    session: SessionDep,
    member: CurrentMember,
    platform: Platform | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    history_days: Annotated[
        int, Query(ge=30, le=730)
    ] = metrics_service.DEFAULT_POST_HISTORY_DAYS,
) -> Any:
    """
    Per platform that has posts: the latest `limit` posts, each metric ranked
    against the posts of the last `history_days`, with the P5 / median / P95
    of that history as benchmarks.
    """
    return metrics_service.post_performance(
        session, member.workspace_id, platform, limit, history_days
    )
