"""
Metrics API — dashboard data for a workspace.

Every endpoint takes the same filters: `workspace_id` (the caller must be a
member), an optional `platform`, and an optional `date_from` / `date_to`
range that defaults to the last 30 days.
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentMember, SessionDep
from app.models.integration import Platform
from app.models.metrics import MetricsSummary, MetricsTimeSeries, PostsPublic
from app.services import metrics as metrics_service
from app.services.metrics import MetricsQuery

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _metrics_query(
    member: CurrentMember,
    platform: Platform | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> MetricsQuery:
    return MetricsQuery.build(member.workspace_id, platform, date_from, date_to)


MetricsQueryDep = Annotated[MetricsQuery, Depends(_metrics_query)]


@router.get("/summary", response_model=MetricsSummary)
def get_summary(session: SessionDep, query: MetricsQueryDep) -> Any:
    """Overall and per-platform KPI totals over the date range."""
    return metrics_service.summarize(session, query)


@router.get("/timeseries", response_model=MetricsTimeSeries)
def get_timeseries(session: SessionDep, query: MetricsQueryDep) -> Any:
    """One data point per calendar day in the range, for charts."""
    return MetricsTimeSeries(data=metrics_service.timeseries(session, query))


@router.get("/posts", response_model=PostsPublic)
def get_top_posts(
    session: SessionDep,
    query: MetricsQueryDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> Any:
    """Top-performing posts (by engagements) published in the date range."""
    posts = metrics_service.top_posts(session, query, limit)
    return PostsPublic(data=posts, count=len(posts))
