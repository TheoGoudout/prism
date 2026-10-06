"""
Helpers shared by the mailing platforms (Mailchimp, Klaviyo, Brevo).

An email campaign is stored as a Post of type `email`, its metrics mapped onto
the normalised fields:

  - impressions: emails delivered (or sent, when delivery isn't reported)
  - views: unique opens
  - engagements: unique clicks, the email's equivalent of interacting with a
    post; the engagement rate (engagements / views) is thus the
    click-to-open rate
  - clicks: total clicks

A mailing list's subscriber count is stored as its followers.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlmodel import Session

from app import crud
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert


def as_int(value: Any) -> int | None:
    """The value as an int, or None if the platform didn't report a number."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value)


def email_campaign_post(
    *,
    external_id: str,
    published_at: datetime,
    subject: str | None,
    permalink: str | None = None,
    delivered: Any = None,
    unique_opens: Any = None,
    unique_clicks: Any = None,
    clicks: Any = None,
    raw_data: dict[str, Any] | None = None,
) -> PostUpsert:
    return PostUpsert(
        external_id=external_id,
        published_at=published_at,
        content_type=ContentType.email,
        text=subject,
        permalink=permalink,
        impressions=as_int(delivered),
        views=as_int(unique_opens),
        engagements=as_int(unique_clicks),
        clicks=as_int(clicks),
        raw_data=raw_data,
    )


def record_subscribers(
    session: Session,
    platform_account_id: uuid.UUID,
    subscribers: Any,
    raw_data: dict[str, Any] | None = None,
) -> None:
    """Store today's subscriber count of a mailing list as its followers."""
    crud.upsert_metric_snapshot(
        session=session,
        platform_account_id=platform_account_id,
        snapshot_in=MetricSnapshotUpsert(
            date=date.today(),
            followers_count=as_int(subscribers),
            raw_data=raw_data,
        ),
    )
