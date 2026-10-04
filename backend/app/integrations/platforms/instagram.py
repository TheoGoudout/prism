"""
Instagram Business sync.

For every Instagram Business account linked to the user's Facebook Pages:
  - the account is stored as a PlatformAccount
  - daily account insights (reach, new followers) and today's follower total
    become MetricSnapshots
  - the 100 most recent posts, reels and stories become Posts

Meta retired the Instagram `impressions`, `video_views` and `engagement`
metrics in 2025; they are replaced by `views` and `total_interactions`.
"""

import logging
import uuid
from datetime import date
from typing import Any

import httpx
from sqlmodel import Session

from app import crud
from app.integrations.common import engagement_total, log_http_errors, parse_datetime
from app.integrations.meta import (
    daily_insights,
    first_value,
    graph_get,
    graph_get_all,
)
from app.models.integration import Integration
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert

logger = logging.getLogger(__name__)

# Account metrics with a daily time series. `follower_count` is the number of
# *new* followers per day.
_ACCOUNT_METRICS = ["reach", "follower_count"]

_MEDIA_METRICS = "views,reach,total_interactions,likes,comments,shares,saved"
_STORY_METRICS = "views,reach"  # stories support fewer metrics

_CONTENT_TYPES: dict[str, ContentType] = {
    "IMAGE": ContentType.post,
    "VIDEO": ContentType.video,
    "CAROUSEL_ALBUM": ContentType.post,
    "REEL": ContentType.reel,
}


def _fetch_instagram_accounts(user_token: str) -> list[dict[str, Any]]:
    """The Instagram Business accounts linked to the user's Facebook Pages."""
    pages = graph_get_all(
        "me/accounts",
        user_token,
        {
            "fields": (
                "id,access_token,instagram_business_account"
                "{id,name,profile_picture_url,username,followers_count}"
            )
        },
    )
    return [
        {
            "ig_id": ig["id"],
            "name": ig.get("name") or ig.get("username") or ig["id"],
            "avatar_url": ig.get("profile_picture_url"),
            "page_token": page.get("access_token", user_token),
            "followers_count": ig.get("followers_count"),
        }
        for page in pages
        if (ig := page.get("instagram_business_account"))
    ]


def _sync_account_insights(
    session: Session,
    platform_account_id: uuid.UUID,
    ig_id: str,
    token: str,
    followers_count: int | None = None,
) -> None:
    by_day = daily_insights(ig_id, token, _ACCOUNT_METRICS)
    # Only the current follower total is available, so record it on today's
    # snapshot; over time this builds up a daily follower history.
    if followers_count is not None:
        by_day.setdefault(date.today(), {})["followers_count"] = followers_count

    for day, values in by_day.items():
        crud.upsert_metric_snapshot(
            session=session,
            platform_account_id=platform_account_id,
            snapshot_in=MetricSnapshotUpsert(
                date=day,
                reach=values.get("reach"),
                followers_count=values.get("followers_count"),
                followers_gained=values.get("follower_count"),
                raw_data=values,
            ),
        )


def _media_insights(media_id: str, media_type: str, token: str) -> dict[str, Any]:
    """{metric name: value}, or {} if Meta won't return insights for the media."""
    metrics = _STORY_METRICS if media_type == "STORY" else _MEDIA_METRICS
    try:
        data = graph_get(f"{media_id}/insights", token, {"metric": metrics})
    except httpx.HTTPStatusError as exc:
        logger.warning("Could not fetch insights for media %s: %s", media_id, exc)
        return {}
    return {entry["name"]: first_value(entry) for entry in data.get("data", [])}


def _sync_media(
    session: Session, platform_account_id: uuid.UUID, ig_id: str, token: str
) -> None:
    data = graph_get(
        f"{ig_id}/media",
        token,
        {
            "fields": "id,media_type,timestamp,caption,permalink,media_url,thumbnail_url",
            "limit": 100,
        },
    )
    for item in data.get("data", []):
        published_at = parse_datetime(item.get("timestamp"))
        if published_at is None:
            logger.warning(
                "Skipping media %s: missing or invalid timestamp", item["id"]
            )
            continue

        media_type: str = item.get("media_type", "IMAGE")
        insights = _media_insights(item["id"], media_type, token)
        likes = insights.get("likes")
        comments = insights.get("comments")
        shares = insights.get("shares")
        saves = insights.get("saved")
        crud.upsert_post(
            session=session,
            platform_account_id=platform_account_id,
            post_in=PostUpsert(
                external_id=item["id"],
                published_at=published_at,
                content_type=_CONTENT_TYPES.get(media_type, ContentType.post),
                text=item.get("caption"),
                media_url=item.get("media_url") or item.get("thumbnail_url"),
                permalink=item.get("permalink"),
                views=insights.get("views"),
                reach=insights.get("reach"),
                # total_interactions is the same sum; it covers posts whose
                # breakdown Meta doesn't return
                engagements=engagement_total(likes, comments, shares, saves)
                or insights.get("total_interactions"),
                likes=likes,
                comments=comments,
                shares=shares,
                saves=saves,
                raw_data=insights or None,
            ),
        )


def sync_instagram(
    session: Session, integration: Integration, access_token: str
) -> None:
    """Sync every Instagram Business account linked to the user's Pages."""
    for ig in _fetch_instagram_accounts(access_token):
        account = crud.upsert_platform_account(
            session=session,
            integration=integration,
            external_id=ig["ig_id"],
            name=ig["name"],
            avatar_url=ig.get("avatar_url"),
            account_type="business",
        )
        with log_http_errors(f"Instagram insights for {ig['ig_id']}"):
            _sync_account_insights(
                session,
                account.id,
                ig["ig_id"],
                ig["page_token"],
                ig.get("followers_count"),
            )
        with log_http_errors(f"Instagram media for {ig['ig_id']}"):
            _sync_media(session, account.id, ig["ig_id"], ig["page_token"])
