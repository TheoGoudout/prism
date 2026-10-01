"""
Twitter/X sync (API v2).

Fetches:
  - Account-level metrics (organic metrics: impressions, engagements, followers)
  - Tweet metrics for the 100 most recent tweets

Uses the OAuth2 Bearer token (access token) stored in the Integration.
The Twitter API v2 user metrics endpoint requires OAuth 2.0 with user context.
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

TWITTER_API = "https://api.twitter.com/2"


# ---------------------------------------------------------------------------
# Internal HTTP helper
# ---------------------------------------------------------------------------


def _get(path: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    resp = httpx.get(
        f"{TWITTER_API}/{path}",
        params=params or {},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    result: dict[str, Any] = resp.json()
    return result


# ---------------------------------------------------------------------------
# Account info
# ---------------------------------------------------------------------------


def _fetch_user_info(token: str) -> dict[str, Any]:
    """Return user data including public_metrics."""
    data = _get(
        "users/me",
        token,
        {"user.fields": ("id,name,username,profile_image_url,public_metrics")},
    )
    user: dict[str, Any] = data.get("data", {})
    return user


# ---------------------------------------------------------------------------
# Account-level metrics (derived from public_metrics, snapshotted daily)
# ---------------------------------------------------------------------------


def _sync_account_snapshot(
    session: Session,
    platform_account_id: Any,
    public_metrics: dict[str, Any],
) -> None:
    """Store today's public metrics as a daily snapshot."""
    today = datetime.now(timezone.utc).date()
    snapshot = MetricSnapshotUpsert(
        date=today,
        followers_count=public_metrics.get("followers_count"),
        posts_count=public_metrics.get("tweet_count"),
        raw_data=public_metrics,
    )
    crud.upsert_metric_snapshot(
        session=session,
        platform_account_id=platform_account_id,
        snapshot_in=snapshot,
    )


# ---------------------------------------------------------------------------
# Tweet metrics
# ---------------------------------------------------------------------------


def _sync_tweets(
    session: Session,
    platform_account_id: Any,
    user_id: str,
    token: str,
) -> None:
    """Fetch the 100 most recent tweets and their organic metrics."""
    # end_time must be at least 10 seconds in the past
    end_time = datetime.now(timezone.utc) - timedelta(seconds=15)
    start_time = end_time - timedelta(days=30)

    resp = _get(
        f"users/{user_id}/tweets",
        token,
        {
            "max_results": 100,
            "tweet.fields": (
                "id,text,created_at,public_metrics,attachments,"
                "entities,referenced_tweets"
            ),
            "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_time": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )

    for tweet in resp.get("data", []):
        tweet_id: str = tweet["id"]
        metrics: dict[str, Any] = tweet.get("public_metrics", {})

        # Retweets (referenced_tweets type=retweeted) are skipped — not owned content
        refs = tweet.get("referenced_tweets", [])
        if any(r.get("type") == "retweeted" for r in refs):
            continue

        try:
            published_at = datetime.fromisoformat(
                tweet["created_at"].replace("Z", "+00:00")
            )
        except (KeyError, ValueError):
            logger.warning("Skipping tweet %s: missing created_at", tweet_id)
            continue

        post = PostUpsert(
            external_id=tweet_id,
            published_at=published_at,
            content_type=ContentType.tweet,
            text=tweet.get("text"),
            impressions=metrics.get("impression_count"),
            engagements=metrics.get("like_count", 0)
            + metrics.get("retweet_count", 0)
            + metrics.get("reply_count", 0)
            + metrics.get("quote_count", 0),
            likes=metrics.get("like_count"),
            comments=metrics.get("reply_count"),
            shares=metrics.get("retweet_count"),
            raw_data=metrics or None,
        )
        crud.upsert_post(
            session=session,
            platform_account_id=platform_account_id,
            post_in=post,
        )


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------


def sync_twitter(session: Session, integration: Integration) -> None:
    """Sync Twitter/X account metrics and recent tweets."""
    token = crud.get_access_token(integration)
    if not token:
        raise ValueError("No access token available for Twitter integration")

    user = _fetch_user_info(token)
    if not user:
        raise ValueError("Could not retrieve Twitter user info")

    user_id: str = user["id"]

    account_in = PlatformAccountCreate(
        integration_id=integration.id,
        workspace_id=integration.workspace_id,
        platform=Platform.twitter,
        external_id=user_id,
        name=user.get("name", user_id),
        avatar_url=user.get("profile_image_url"),
        account_type="user",
    )
    account = crud.upsert_platform_account(session=session, account_in=account_in)

    public_metrics: dict[str, Any] = user.get("public_metrics", {})
    if public_metrics:
        _sync_account_snapshot(session, account.id, public_metrics)

    try:
        _sync_tweets(session, account.id, user_id, token)
    except httpx.HTTPStatusError as exc:
        logger.error("sync_twitter: tweet fetch error for user %s: %s", user_id, exc)


# Register with the Celery sync dispatcher (side-effect on import)
register_platform_sync(Platform.twitter.value, sync_twitter)
