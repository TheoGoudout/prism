"""Storage for synced metrics: daily account snapshots and per-post metrics."""

import math
import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.core.config import settings
from app.crud.common import save
from app.models.common import get_datetime_utc
from app.models.integration import PlatformAccount
from app.models.metrics import (
    ContentMetrics,
    MetricSnapshot,
    MetricSnapshotUpsert,
    Post,
    PostUpsert,
)


def _engagement_rate(metrics: ContentMetrics) -> float | None:
    """
    engagements / exposures (views, or impressions), or None if either is
    unknown. Unlike reach, every platform reports exposures for its posts.
    """
    if metrics.engagements is not None and metrics.exposures:
        return round(metrics.engagements / metrics.exposures, 6)
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


def _track_engagement(post: Post) -> None:
    """
    Record a new interaction when the post's engagements grew by
    SYNC_MIN_ENGAGEMENT_GROWTH (at least SYNC_MIN_NEW_ENGAGEMENTS) since the
    last one: relative growth puts a popular account's post and a small one's
    on the same footing. Gains add up across syncs, so frequent syncs each
    seeing a few still count.
    """
    if post.engagements is None:
        return
    if post.engagements_at_last_engaged is None:
        post.engagements_at_last_engaged = post.engagements
        return
    baseline = post.engagements_at_last_engaged
    needed = max(
        settings.SYNC_MIN_NEW_ENGAGEMENTS,
        math.ceil(baseline * settings.SYNC_MIN_ENGAGEMENT_GROWTH),
    )
    if post.engagements - baseline >= needed:
        post.last_engaged_at = get_datetime_utc()
        post.engagements_at_last_engaged = post.engagements


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
        # Publication is the post's first interaction
        post = Post(
            platform_account_id=platform_account_id,
            last_engaged_at=post_in.published_at,
            engagements_at_last_engaged=post_in.engagements,
            **data,
        )
    else:
        _apply(post, data)
        _track_engagement(post)
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


def get_posts_for_accounts(
    *,
    session: Session,
    platform_account_ids: Sequence[uuid.UUID],
    start_date: date,
    end_date: date,
) -> Sequence[Post]:
    """Posts several accounts published over a date range, oldest first."""
    if not platform_account_ids:
        return []
    statement = (
        select(Post)
        .where(col(Post.platform_account_id).in_(platform_account_ids))
        .where(func.date(Post.published_at) >= start_date)
        .where(func.date(Post.published_at) <= end_date)
        .order_by(col(Post.published_at))
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


def merge_imported_snapshots(
    *,
    session: Session,
    platform_account_id: uuid.UUID,
    snapshots: Sequence[MetricSnapshotUpsert],
    source: str,
) -> tuple[int, int]:
    """
    Store daily snapshots imported from a file, in one transaction. Returns
    how many were created and updated.
    """
    by_date = {s.date: s for s in snapshots}  # a repeated day: the last row wins
    existing = session.exec(
        select(MetricSnapshot).where(
            MetricSnapshot.platform_account_id == platform_account_id,
            col(MetricSnapshot.date).in_(by_date),
        )
    ).all()
    return _merge_imported(
        session,
        MetricSnapshot,
        platform_account_id,
        {row.date: row for row in existing},
        by_date,
        source,
    )


def merge_imported_posts(
    *,
    session: Session,
    platform_account_id: uuid.UUID,
    posts: Sequence[PostUpsert],
    source: str,
) -> tuple[int, int]:
    """
    Store posts imported from a file, in one transaction; a post the sync
    already stored (same external ID) is completed. Returns how many were
    created and updated.
    """
    by_id = {p.external_id: p for p in posts}
    existing = session.exec(
        select(Post).where(
            Post.platform_account_id == platform_account_id,
            col(Post.external_id).in_(by_id),
        )
    ).all()
    return _merge_imported(
        session,
        Post,
        platform_account_id,
        {row.external_id: row for row in existing},
        by_id,
        source,
    )


def _merge_imported[RowT: (MetricSnapshot, Post)](
    session: Session,
    model: type[RowT],
    platform_account_id: uuid.UUID,
    existing: dict[Any, RowT],
    incoming: dict[Any, MetricSnapshotUpsert] | dict[Any, PostUpsert],
    source: str,
) -> tuple[int, int]:
    """
    Unlike a sync, an import only fills in: a value the file doesn't have
    never erases one already stored.
    """
    created = 0
    for key, item in incoming.items():
        data = {
            name: value
            for name, value in item.model_dump(exclude={"raw_data"}).items()
            if value is not None
        }
        row = existing.get(key)
        if row is None:
            row = model(platform_account_id=platform_account_id, **data)
            created += 1
        else:
            for name, value in data.items():
                setattr(row, name, value)
        row.raw_data = {**(row.raw_data or {}), "imported_from": source}
        row.engagement_rate = _engagement_rate(row)
        session.add(row)
    session.commit()
    return created, len(incoming) - created
