"""
When to sync an integration again, on top of the nightly sync.

A post gets most of its engagement in its first hours, so the integration is
synced again soon after a post is published, then less and less often: the
time to the next sync is the time since its posts' latest interaction (the
publication of a post, or a sync seeing it gain SYNC_MIN_NEW_ENGAGEMENTS),
kept between SYNC_MIN_INTERVAL_MINUTES and SYNC_MAX_INTERVAL_HOURS. A post
that keeps gaining engagement therefore keeps the syncs frequent, and a quiet
one spaces them out. Follow-up syncs stop after SYNC_QUIET_DAYS without any
interaction, and only posts published in the last SYNC_FOLLOW_POST_DAYS are
followed; the nightly sync carries on regardless.
"""

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.core.config import settings
from app.models.integration import Integration, PlatformAccount
from app.models.metrics import Post


def latest_interaction(
    session: Session, integration: Integration, now: datetime
) -> datetime | None:
    """The latest interaction with the integration's recently published posts."""
    since = now - timedelta(days=settings.SYNC_FOLLOW_POST_DAYS)
    statement = (
        select(
            func.max(func.coalesce(col(Post.last_engaged_at), col(Post.published_at)))
        )
        .join(PlatformAccount)
        .where(PlatformAccount.integration_id == integration.id)
        .where(col(PlatformAccount.is_active).is_(True))
        .where(col(Post.published_at) >= since)
    )
    return session.exec(statement).one()


def next_sync_at(last_interaction: datetime | None, now: datetime) -> datetime | None:
    """When to sync again, or None to leave it to the nightly sync."""
    if last_interaction is None:
        return None
    quiet_for = max(now - last_interaction, timedelta(0))
    if quiet_for >= timedelta(days=settings.SYNC_QUIET_DAYS):
        return None
    interval = min(
        max(quiet_for, timedelta(minutes=settings.SYNC_MIN_INTERVAL_MINUTES)),
        timedelta(hours=settings.SYNC_MAX_INTERVAL_HOURS),
    )
    return now + interval


def schedule_next_sync(
    session: Session, integration: Integration, now: datetime
) -> datetime | None:
    """Set when to sync the integration again after a sync that ended ``now``."""
    integration.next_sync_at = next_sync_at(
        latest_interaction(session, integration, now), now
    )
    return integration.next_sync_at
