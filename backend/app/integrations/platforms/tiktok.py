"""
TikTok sync (Display API, open.tiktokapis.com/v2).

  - the creator account is stored as a PlatformAccount
  - today's follower and video counts become a MetricSnapshot
  - videos published in the sync window (latest 20) become Posts

The Display API takes the requested `fields` as a comma-separated query
parameter; request options (e.g. max_count) go in the JSON body.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session

from app import crud
from app.integrations.common import SYNC_WINDOW_DAYS, log_http_errors, sum_known
from app.integrations.http import get_json, post_json
from app.models.integration import Integration
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert

TIKTOK_API = "https://open.tiktokapis.com/v2"

_USER_FIELDS = "open_id,display_name,avatar_url,follower_count,video_count"
_VIDEO_FIELDS = (
    "id,title,create_time,share_url,cover_image_url,video_description,duration,"
    "view_count,like_count,comment_count,share_count"
)
_VIDEO_METRICS = ("view_count", "like_count", "comment_count", "share_count")


def _fetch_user_info(token: str) -> dict[str, Any]:
    data = get_json(
        f"{TIKTOK_API}/user/info/", token=token, params={"fields": _USER_FIELDS}
    )
    user: dict[str, Any] = data.get("data", {}).get("user", {})
    return user


def _sync_account_snapshot(
    session: Session, platform_account_id: uuid.UUID, user_info: dict[str, Any]
) -> None:
    crud.upsert_metric_snapshot(
        session=session,
        platform_account_id=platform_account_id,
        snapshot_in=MetricSnapshotUpsert(
            date=date.today(),
            followers_count=user_info.get("follower_count"),
            posts_count=user_info.get("video_count"),
            raw_data={
                k: user_info[k]
                for k in ("follower_count", "video_count")
                if k in user_info
            },
        ),
    )


def _sync_videos(session: Session, platform_account_id: uuid.UUID, token: str) -> None:
    window_start = datetime.now(timezone.utc) - timedelta(days=SYNC_WINDOW_DAYS)
    data = post_json(
        f"{TIKTOK_API}/video/list/",
        token=token,
        params={"fields": _VIDEO_FIELDS},
        body={"max_count": 20},
    )
    for video in data.get("data", {}).get("videos", []):
        if not video.get("id"):
            continue
        try:
            published_at = datetime.fromtimestamp(video["create_time"], tz=timezone.utc)
        except (KeyError, TypeError, ValueError):
            continue
        if published_at < window_start:
            continue

        likes = video.get("like_count")
        comments = video.get("comment_count")
        shares = video.get("share_count")
        crud.upsert_post(
            session=session,
            platform_account_id=platform_account_id,
            post_in=PostUpsert(
                external_id=video["id"],
                published_at=published_at,
                content_type=ContentType.video,
                text=video.get("video_description") or video.get("title"),
                media_url=video.get("cover_image_url"),
                permalink=video.get("share_url"),
                views=video.get("view_count"),
                engagements=sum_known(likes, comments, shares),
                likes=likes,
                comments=comments,
                shares=shares,
                raw_data={k: video[k] for k in _VIDEO_METRICS if k in video} or None,
            ),
        )


def sync_tiktok(session: Session, integration: Integration, access_token: str) -> None:
    """Sync the TikTok creator account and its recent videos."""
    user_info = _fetch_user_info(access_token)
    if not user_info:
        raise ValueError("Could not retrieve TikTok user info")

    open_id: str = user_info.get("open_id", integration.external_account_id)
    account = crud.upsert_platform_account(
        session=session,
        integration=integration,
        external_id=open_id,
        name=user_info.get("display_name", open_id),
        avatar_url=user_info.get("avatar_url"),
        account_type="creator",
    )
    _sync_account_snapshot(session, account.id, user_info)
    with log_http_errors("TikTok videos"):
        _sync_videos(session, account.id, access_token)
