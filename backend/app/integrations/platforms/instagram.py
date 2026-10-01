"""
Instagram Business sync.

Fetches:
  - Instagram Business accounts linked to Facebook Pages → PlatformAccounts
  - Account-level daily insights (impressions, reach, follower count, profile views)
  - Media metrics for up to 100 recent posts/reels/stories

Uses the Facebook Graph API with the user access token from the Integration.

Meta retired the Instagram `impressions`, `video_views` and `engagement`
metrics in 2025; they are replaced by `views` and `total_interactions`.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlmodel import Session

from app import crud
from app.integrations.meta import GRAPH_API
from app.models.integration import Integration, Platform, PlatformAccountCreate
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert
from app.worker.tasks.sync import register_platform_sync

logger = logging.getLogger(__name__)

# Account-level metrics that support a daily (period=day) time series.
# `follower_count` is the number of *new* followers per day.
_ACCOUNT_METRICS = ",".join(["reach", "follower_count"])

# Media-level metrics available for feed posts and reels
_MEDIA_METRICS = ",".join(
    [
        "views",
        "reach",
        "total_interactions",
        "likes",
        "comments",
        "shares",
        "saved",
    ]
)

# Metrics for stories (different endpoint, limited set)
_STORY_METRICS = ",".join(["views", "reach"])

_MEDIA_TYPE_MAP: dict[str, ContentType] = {
    "IMAGE": ContentType.post,
    "VIDEO": ContentType.video,
    "CAROUSEL_ALBUM": ContentType.post,
    "REEL": ContentType.reel,
}


# ---------------------------------------------------------------------------
# Internal HTTP helper
# ---------------------------------------------------------------------------


def _get(path: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    p: dict[str, Any] = dict(params or {})
    p["access_token"] = token
    resp = httpx.get(f"{GRAPH_API}/{path}", params=p, timeout=15)
    resp.raise_for_status()
    result: dict[str, Any] = resp.json()
    return result


# ---------------------------------------------------------------------------
# Account discovery
# ---------------------------------------------------------------------------


def _fetch_instagram_accounts(user_token: str) -> list[dict[str, Any]]:
    """
    Return Instagram Business accounts linked to the user's Facebook Pages.
    Each entry has: ig_id, name, avatar_url, page_access_token.
    """
    pages_resp = _get(
        "me/accounts",
        user_token,
        {
            "fields": (
                "id,access_token,"
                "instagram_business_account"
                "{id,name,profile_picture_url,username,followers_count}"
            )
        },
    )

    accounts = []
    for page in pages_resp.get("data", []):
        ig = page.get("instagram_business_account")
        if not ig:
            continue
        accounts.append(
            {
                "ig_id": ig["id"],
                "name": ig.get("name") or ig.get("username") or ig["id"],
                "avatar_url": ig.get("profile_picture_url"),
                "page_token": page.get("access_token", user_token),
                "followers_count": ig.get("followers_count"),
            }
        )
    return accounts


# ---------------------------------------------------------------------------
# Account-level daily insights
# ---------------------------------------------------------------------------


def _sync_account_insights(
    session: Session,
    platform_account_id: Any,
    ig_id: str,
    token: str,
    followers_count: int | None = None,
) -> None:
    end = date.today()
    start = end - timedelta(days=30)

    resp = _get(
        f"{ig_id}/insights",
        token,
        {
            "metric": _ACCOUNT_METRICS,
            "period": "day",
            "since": int(
                datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()
            ),
            "until": int(
                datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp()
            ),
        },
    )

    by_date: dict[date, dict[str, Any]] = {}
    for entry in resp.get("data", []):
        metric_name: str = entry["name"]
        for val_item in entry.get("values", []):
            try:
                d = datetime.fromisoformat(
                    val_item["end_time"].replace("Z", "+00:00")
                ).date()
            except (KeyError, ValueError):
                continue
            by_date.setdefault(d, {})[metric_name] = val_item["value"]

    # The API only exposes the current follower total, so record it on today's
    # snapshot; over time this builds up a daily follower history.
    if followers_count is not None:
        by_date.setdefault(end, {})["followers_count"] = followers_count

    for d, vals in by_date.items():
        snapshot = MetricSnapshotUpsert(
            date=d,
            reach=vals.get("reach"),
            followers_count=vals.get("followers_count"),
            followers_gained=vals.get("follower_count"),
            raw_data=vals,
        )
        crud.upsert_metric_snapshot(
            session=session,
            platform_account_id=platform_account_id,
            snapshot_in=snapshot,
        )


# ---------------------------------------------------------------------------
# Media (posts, reels, stories)
# ---------------------------------------------------------------------------


def _sync_media(
    session: Session,
    platform_account_id: Any,
    ig_id: str,
    token: str,
) -> None:
    resp = _get(
        f"{ig_id}/media",
        token,
        {
            "fields": (
                "id,media_type,timestamp,caption,permalink,"
                "media_url,thumbnail_url"
            ),
            "limit": 100,
        },
    )

    for item in resp.get("data", []):
        media_id: str = item["id"]
        media_type: str = item.get("media_type", "IMAGE")
        content_type = _MEDIA_TYPE_MAP.get(media_type, ContentType.post)

        # Stories have a different insights endpoint and limited metrics
        metrics_param = _STORY_METRICS if media_type == "STORY" else _MEDIA_METRICS

        mvals: dict[str, Any] = {}
        try:
            ins_resp = _get(
                f"{media_id}/insights",
                token,
                {"metric": metrics_param},
            )
            for entry in ins_resp.get("data", []):
                mvals[entry["name"]] = entry.get("values", [{}])[0].get("value")
        except httpx.HTTPStatusError as exc:
            logger.warning("Could not fetch insights for media %s: %s", media_id, exc)

        try:
            published_at = datetime.fromisoformat(
                item["timestamp"].replace("Z", "+00:00")
            )
        except (KeyError, ValueError):
            logger.warning("Skipping media %s: missing or invalid timestamp", media_id)
            continue

        media_url = item.get("media_url") or item.get("thumbnail_url")

        post = PostUpsert(
            external_id=media_id,
            published_at=published_at,
            content_type=content_type,
            text=item.get("caption"),
            media_url=media_url,
            permalink=item.get("permalink"),
            views=mvals.get("views"),
            reach=mvals.get("reach"),
            engagements=mvals.get("total_interactions"),
            likes=mvals.get("likes"),
            comments=mvals.get("comments"),
            shares=mvals.get("shares"),
            saves=mvals.get("saved"),
            raw_data=mvals or None,
        )
        crud.upsert_post(
            session=session,
            platform_account_id=platform_account_id,
            post_in=post,
        )


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------


def sync_instagram(session: Session, integration: Integration) -> None:
    """Sync all Instagram Business accounts linked to the integration."""
    user_token = crud.get_access_token(integration)
    if not user_token:
        raise ValueError("No access token available for Instagram integration")

    accounts = _fetch_instagram_accounts(user_token)
    if not accounts:
        logger.info(
            "sync_instagram: no Instagram Business accounts for integration %s",
            integration.id,
        )
        return

    for acc in accounts:
        ig_id: str = acc["ig_id"]
        token: str = acc["page_token"]

        account_in = PlatformAccountCreate(
            integration_id=integration.id,
            workspace_id=integration.workspace_id,
            platform=Platform.instagram,
            external_id=ig_id,
            name=acc["name"],
            avatar_url=acc.get("avatar_url"),
            account_type="business",
        )
        account = crud.upsert_platform_account(session=session, account_in=account_in)

        try:
            _sync_account_insights(
                session, account.id, ig_id, token, acc.get("followers_count")
            )
        except httpx.HTTPStatusError as exc:
            logger.error("sync_instagram: insights error for %s: %s", ig_id, exc)

        try:
            _sync_media(session, account.id, ig_id, token)
        except httpx.HTTPStatusError as exc:
            logger.error("sync_instagram: media error for %s: %s", ig_id, exc)


# Register with the Celery sync dispatcher (side-effect on import)
register_platform_sync(Platform.instagram.value, sync_instagram)
