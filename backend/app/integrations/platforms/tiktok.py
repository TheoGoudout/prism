"""
TikTok Business API sync.

Fetches:
  - Creator account info → PlatformAccount
  - Account-level daily stats (followers, profile views, video views)
  - Video-level metrics for the 20 most recent videos

Uses the TikTok Research API (open.tiktokapis.com/v2) with the Bearer token
from the Integration.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlmodel import Session

from app import crud
from app.models.integration import Integration, Platform, PlatformAccountCreate
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert
from app.worker.tasks.sync import register_platform_sync

logger = logging.getLogger(__name__)

TIKTOK_API = "https://open.tiktokapis.com/v2"


# ---------------------------------------------------------------------------
# Internal HTTP helpers
# ---------------------------------------------------------------------------


# The Display API takes the requested `fields` as a comma-separated query
# parameter; request options (e.g. max_count) go in the JSON body.


def _get(path: str, token: str, fields: list[str]) -> dict[str, Any]:
    resp = httpx.get(
        f"{TIKTOK_API}/{path}",
        params={"fields": ",".join(fields)},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    result: dict[str, Any] = resp.json()
    return result


def _post(
    path: str, token: str, fields: list[str], body: dict[str, Any]
) -> dict[str, Any]:
    resp = httpx.post(
        f"{TIKTOK_API}/{path}",
        params={"fields": ",".join(fields)},
        json=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    result: dict[str, Any] = resp.json()
    return result


# ---------------------------------------------------------------------------
# Account info
# ---------------------------------------------------------------------------


def _fetch_user_info(token: str) -> dict[str, Any]:
    data = _get(
        "user/info/",
        token,
        ["open_id", "display_name", "avatar_url", "follower_count", "video_count"],
    )
    user: dict[str, Any] = data.get("data", {}).get("user", {})
    return user


# ---------------------------------------------------------------------------
# Account-level daily snapshot
# ---------------------------------------------------------------------------


def _sync_account_snapshot(
    session: Session,
    platform_account_id: Any,
    user_info: dict[str, Any],
) -> None:
    today = datetime.now(timezone.utc).date()
    snapshot = MetricSnapshotUpsert(
        date=today,
        followers_count=user_info.get("follower_count"),
        posts_count=user_info.get("video_count"),
        raw_data={
            k: user_info[k] for k in ("follower_count", "video_count") if k in user_info
        },
    )
    crud.upsert_metric_snapshot(
        session=session,
        platform_account_id=platform_account_id,
        snapshot_in=snapshot,
    )


# ---------------------------------------------------------------------------
# Video metrics
# ---------------------------------------------------------------------------


def _sync_videos(
    session: Session,
    platform_account_id: Any,
    token: str,
) -> None:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)

    resp = _post(
        "video/list/",
        token,
        [
            "id",
            "title",
            "create_time",
            "share_url",
            "cover_image_url",
            "video_description",
            "duration",
            "view_count",
            "like_count",
            "comment_count",
            "share_count",
        ],
        {"max_count": 20},
    )

    for video in resp.get("data", {}).get("videos", []):
        video_id: str = video.get("id", "")
        if not video_id:
            continue

        created_ts = video.get("create_time", 0)
        try:
            published_at = datetime.fromtimestamp(created_ts, tz=timezone.utc)
        except (TypeError, ValueError):
            published_at = datetime.now(timezone.utc)

        # Filter to 30-day window
        if published_at < start:
            continue

        view_count = video.get("view_count")
        like_count = video.get("like_count")
        comment_count = video.get("comment_count")
        share_count = video.get("share_count")

        engagements: int | None = None
        if any(v is not None for v in (like_count, comment_count, share_count)):
            engagements = (like_count or 0) + (comment_count or 0) + (share_count or 0)

        post = PostUpsert(
            external_id=video_id,
            published_at=published_at,
            content_type=ContentType.video,
            text=video.get("video_description") or video.get("title"),
            media_url=video.get("cover_image_url"),
            permalink=video.get("share_url"),
            views=view_count,
            engagements=engagements,
            likes=like_count,
            comments=comment_count,
            shares=share_count,
            raw_data={
                k: video[k]
                for k in ("view_count", "like_count", "comment_count", "share_count")
                if k in video
            }
            or None,
        )
        crud.upsert_post(
            session=session,
            platform_account_id=platform_account_id,
            post_in=post,
        )


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------


def sync_tiktok(session: Session, integration: Integration) -> None:
    """Sync TikTok account metrics and recent videos."""
    token = crud.get_access_token(integration)
    if not token:
        raise ValueError("No access token available for TikTok integration")

    user_info = _fetch_user_info(token)
    if not user_info:
        raise ValueError("Could not retrieve TikTok user info")

    open_id: str = user_info.get("open_id", integration.external_account_id or "")

    account_in = PlatformAccountCreate(
        integration_id=integration.id,
        workspace_id=integration.workspace_id,
        platform=Platform.tiktok,
        external_id=open_id,
        name=user_info.get("display_name", open_id),
        avatar_url=user_info.get("avatar_url"),
        account_type="creator",
    )
    account = crud.upsert_platform_account(session=session, account_in=account_in)

    _sync_account_snapshot(session, account.id, user_info)

    try:
        _sync_videos(session, account.id, token)
    except httpx.HTTPStatusError as exc:
        logger.error("sync_tiktok: video fetch error: %s", exc)


# Register with the Celery sync dispatcher (side-effect on import)
register_platform_sync(Platform.tiktok.value, sync_tiktok)
