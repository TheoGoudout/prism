"""
CRUD helpers for MetricSnapshot and Post.

These are called by sync tasks (Steps 6-11), not by users directly.
The read helpers will be used by the dashboard API (Step 12+).
"""

import uuid
from collections.abc import Sequence
from datetime import date as date_type

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.metrics import (
    ContentType,
    MetricSnapshot,
    MetricSnapshotUpsert,
    Post,
    PostUpsert,
)


def _compute_engagement_rate(data: MetricSnapshotUpsert | PostUpsert) -> float | None:
    """engagement_rate = engagements / reach, or None if data is insufficient."""
    if data.engagements is not None and data.reach:
        return round(data.engagements / data.reach, 6)
    return None


# ---------------------------------------------------------------------------
# MetricSnapshot
# ---------------------------------------------------------------------------


def upsert_metric_snapshot(
    *,
    session: Session,
    platform_account_id: uuid.UUID,
    snapshot_in: MetricSnapshotUpsert,
) -> MetricSnapshot:
    """Insert a daily snapshot or overwrite it if one already exists."""
    existing = session.exec(
        select(MetricSnapshot).where(
            MetricSnapshot.platform_account_id == platform_account_id,
            MetricSnapshot.date == snapshot_in.date,
        )
    ).first()

    data = snapshot_in.model_dump(exclude_unset=False)
    data["engagement_rate"] = _compute_engagement_rate(snapshot_in)
    data["platform_account_id"] = platform_account_id

    if existing:
        for key, value in data.items():
            if value is not None or key == "raw_data":
                setattr(existing, key, value)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    snapshot = MetricSnapshot(**data)
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def get_snapshots(
    *,
    session: Session,
    platform_account_id: uuid.UUID,
    start_date: date_type,
    end_date: date_type,
) -> Sequence[MetricSnapshot]:
    statement = (
        select(MetricSnapshot)
        .where(MetricSnapshot.platform_account_id == platform_account_id)
        .where(MetricSnapshot.date >= start_date)
        .where(MetricSnapshot.date <= end_date)
        .order_by(col(MetricSnapshot.date))
    )
    return session.exec(statement).all()


def get_snapshots_for_accounts(
    *,
    session: Session,
    platform_account_ids: list[uuid.UUID],
    start_date: date_type,
    end_date: date_type,
) -> Sequence[MetricSnapshot]:
    """Bulk-fetch snapshots for multiple accounts (used by dashboard aggregation)."""
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


def get_latest_snapshot(
    *, session: Session, platform_account_id: uuid.UUID
) -> MetricSnapshot | None:
    statement = (
        select(MetricSnapshot)
        .where(MetricSnapshot.platform_account_id == platform_account_id)
        .order_by(col(MetricSnapshot.date).desc())
        .limit(1)
    )
    return session.exec(statement).first()


# ---------------------------------------------------------------------------
# Post
# ---------------------------------------------------------------------------


def upsert_post(
    *,
    session: Session,
    platform_account_id: uuid.UUID,
    post_in: PostUpsert,
) -> Post:
    """Insert a post or update its metrics if it already exists."""
    existing = session.exec(
        select(Post).where(
            Post.platform_account_id == platform_account_id,
            Post.external_id == post_in.external_id,
        )
    ).first()

    data = post_in.model_dump(exclude_unset=False)
    data["engagement_rate"] = _compute_engagement_rate(post_in)
    data["platform_account_id"] = platform_account_id

    if existing:
        for key, value in data.items():
            if value is not None or key in ("raw_data", "text"):
                setattr(existing, key, value)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    post = Post(**data)
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


def get_posts(
    *,
    session: Session,
    platform_account_id: uuid.UUID,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
    content_type: ContentType | None = None,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "published_at",
    descending: bool = True,
) -> tuple[Sequence[Post], int]:
    """Return paginated posts with optional filters."""
    base = select(Post).where(Post.platform_account_id == platform_account_id)

    if start_date:
        base = base.where(func.date(Post.published_at) >= start_date)
    if end_date:
        base = base.where(func.date(Post.published_at) <= end_date)
    if content_type:
        base = base.where(Post.content_type == content_type)

    # Ordering
    count = session.exec(select(func.count()).select_from(base.subquery())).one()

    sort_column = col(getattr(Post, order_by, Post.published_at))
    base = base.order_by(sort_column.desc() if descending else sort_column.asc())
    rows = session.exec(base.offset(offset).limit(limit)).all()
    return rows, count


def get_top_posts(
    *,
    session: Session,
    platform_account_ids: list[uuid.UUID],
    start_date: date_type,
    end_date: date_type,
    metric: str = "engagements",
    limit: int = 10,
) -> Sequence[Post]:
    """Return the top-performing posts across a set of accounts."""
    if not platform_account_ids:
        return []
    sort_column = col(getattr(Post, metric, Post.engagements))
    statement = (
        select(Post)
        .where(col(Post.platform_account_id).in_(platform_account_ids))
        .where(func.date(Post.published_at) >= start_date)
        .where(func.date(Post.published_at) <= end_date)
        .where(sort_column.is_not(None))
        .order_by(sort_column.desc())
        .limit(limit)
    )
    return session.exec(statement).all()
