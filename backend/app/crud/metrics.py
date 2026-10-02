"""Storage for synced metrics: daily account snapshots and per-post metrics."""

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.crud.common import save
from app.models.integration import PlatformAccount
from app.models.metrics import (
    ContentMetrics,
    MetricSnapshot,
    MetricSnapshotUpsert,
    Post,
    PostUpsert,
)


def _engagement_rate(metrics: ContentMetrics) -> float | None:
    """engagements / reach, or None if either is unknown."""
    if metrics.engagements is not None and metrics.reach:
        return round(metrics.engagements / metrics.reach, 6)
    return None


def _apply(row: MetricSnapshot | Post, data: dict[str, Any]) -> None:
    """
    Copy synced values onto an existing row. A metric the platform didn't
    return this time (None) doesn't erase the value stored by an earlier sync;
    raw_data and text always reflect the latest sync.
    """
    for key, value in data.items():
        if value is not None or key in ("raw_data", "text"):
            setattr(row, key, value)


def upsert_metric_snapshot(
    *,
    session: Session,
    platform_account_id: uuid.UUID,
    snapshot_in: MetricSnapshotUpsert,
) -> MetricSnapshot:
    """Insert the account's snapshot for a day, or update it."""
    data = snapshot_in.model_dump()
    data["engagement_rate"] = _engagement_rate(snapshot_in)

    snapshot = session.exec(
        select(MetricSnapshot).where(
            MetricSnapshot.platform_account_id == platform_account_id,
            MetricSnapshot.date == snapshot_in.date,
        )
    ).first()
    if snapshot is None:
        snapshot = MetricSnapshot(platform_account_id=platform_account_id, **data)
    else:
        _apply(snapshot, data)
    return save(session, snapshot)


def upsert_post(
    *,
    session: Session,
    platform_account_id: uuid.UUID,
    post_in: PostUpsert,
) -> Post:
    """Insert a post, or update its content and metrics."""
    data = post_in.model_dump()
    data["engagement_rate"] = _engagement_rate(post_in)

    post = session.exec(
        select(Post).where(
            Post.platform_account_id == platform_account_id,
            Post.external_id == post_in.external_id,
        )
    ).first()
    if post is None:
        post = Post(platform_account_id=platform_account_id, **data)
    else:
        _apply(post, data)
    return save(session, post)


def get_snapshots_for_accounts(
    *,
    session: Session,
    platform_account_ids: Sequence[uuid.UUID],
    start_date: date,
    end_date: date,
) -> Sequence[MetricSnapshot]:
    """Snapshots of several accounts over a date range, oldest first."""
    if not platform_account_ids:
        return []
    statement = (
        select(MetricSnapshot)
        .where(col(MetricSnapshot.platform_account_id).in_(platform_account_ids))
        .where(MetricSnapshot.date >= start_date)
        .where(MetricSnapshot.date <= end_date)
        .order_by(col(MetricSnapshot.date))
    )
    return session.exec(statement).all()


def get_top_posts(
    *,
    session: Session,
    platform_account_ids: Sequence[uuid.UUID],
    start_date: date,
    end_date: date,
    limit: int = 10,
) -> Sequence[Post]:
    """Most-engaging posts published by the accounts over a date range."""
    if not platform_account_ids:
        return []
    statement = (
        select(Post)
        .where(col(Post.platform_account_id).in_(platform_account_ids))
        .where(func.date(Post.published_at) >= start_date)
        .where(func.date(Post.published_at) <= end_date)
        .where(col(Post.engagements).is_not(None))
        .order_by(col(Post.engagements).desc())
        .limit(limit)
    )
    return session.exec(statement).all()


def get_posts(
    *,
    session: Session,
    platform_account_ids: Sequence[uuid.UUID],
    start_date: date,
    end_date: date,
    limit: int,
) -> Sequence[Post]:
    """Posts published by the accounts over a date range, most engaging first."""
    if not platform_account_ids:
        return []
    statement = (
        select(Post)
        .where(col(Post.platform_account_id).in_(platform_account_ids))
        .where(func.date(Post.published_at) >= start_date)
        .where(func.date(Post.published_at) <= end_date)
        .order_by(col(Post.engagements).desc().nulls_last(), col(Post.published_at))
        .limit(limit)
    )
    return session.exec(statement).all()


def get_posts_by_ids(
    *, session: Session, post_ids: Sequence[uuid.UUID], workspace_id: uuid.UUID
) -> Sequence[Post]:
    """The posts among ``post_ids`` that belong to the workspace."""
    if not post_ids:
        return []
    statement = (
        select(Post)
        .join(PlatformAccount)
        .where(col(Post.id).in_(post_ids))
        .where(PlatformAccount.workspace_id == workspace_id)
    )
    return session.exec(statement).all()
