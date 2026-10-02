"""
Twitter/X sync (API v2, OAuth 2.0 user context).

  - the user's profile is stored as a PlatformAccount
  - today's public metrics (followers, tweet count) become a MetricSnapshot
  - their own tweets from the sync window (latest 100, no retweets) become Posts
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlmodel import Session

from app import crud
from app.integrations.common import (
    SYNC_WINDOW_DAYS,
    engagement_total,
    log_http_errors,
    parse_datetime,
    sum_known,
)
from app.integrations.http import get_json
from app.models.integration import Integration
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert

logger = logging.getLogger(__name__)

TWITTER_API = "https://api.twitter.com/2"


def _api_time(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_user_info(token: str) -> dict[str, Any]:
    data = get_json(
        f"{TWITTER_API}/users/me",
        token=token,
        params={"user.fields": "id,name,username,profile_image_url,public_metrics"},
    )
    user: dict[str, Any] = data.get("data", {})
    return user


def _sync_account_snapshot(
    session: Session, platform_account_id: uuid.UUID, public_metrics: dict[str, Any]
) -> None:
    crud.upsert_metric_snapshot(
        session=session,
        platform_account_id=platform_account_id,
        snapshot_in=MetricSnapshotUpsert(
            date=date.today(),
            followers_count=public_metrics.get("followers_count"),
            posts_count=public_metrics.get("tweet_count"),
            raw_data=public_metrics,
        ),
    )


def _sync_tweets(
    session: Session, platform_account_id: uuid.UUID, user_id: str, token: str
) -> None:
    # end_time must be at least 10 seconds in the past
    end_time = datetime.now(UTC) - timedelta(seconds=15)
    data = get_json(
        f"{TWITTER_API}/users/{user_id}/tweets",
        token=token,
        params={
            "max_results": 100,
            "tweet.fields": "id,text,created_at,public_metrics,referenced_tweets",
            "start_time": _api_time(end_time - timedelta(days=SYNC_WINDOW_DAYS)),
            "end_time": _api_time(end_time),
        },
    )
    for tweet in data.get("data", []):
        # Retweets aren't the account's own content
        if any(
            r.get("type") == "retweeted" for r in tweet.get("referenced_tweets", [])
        ):
            continue
        published_at = parse_datetime(tweet.get("created_at"))
        if published_at is None:
            logger.warning("Skipping tweet %s: missing created_at", tweet["id"])
            continue

        metrics: dict[str, Any] = tweet.get("public_metrics", {})
        likes = metrics.get("like_count")
        replies = metrics.get("reply_count")
        # Quotes are shares with a comment
        shares = sum_known(metrics.get("retweet_count"), metrics.get("quote_count"))
        bookmarks = metrics.get("bookmark_count")
        crud.upsert_post(
            session=session,
            platform_account_id=platform_account_id,
            post_in=PostUpsert(
                external_id=tweet["id"],
                published_at=published_at,
                content_type=ContentType.tweet,
                text=tweet.get("text"),
                impressions=metrics.get("impression_count"),
                engagements=engagement_total(likes, replies, shares, bookmarks),
                likes=likes,
                comments=replies,
                shares=shares,
                saves=bookmarks,
                raw_data=metrics or None,
            ),
        )


def sync_twitter(session: Session, integration: Integration, access_token: str) -> None:
    """Sync the Twitter/X profile and its recent tweets."""
    user = _fetch_user_info(access_token)
    if not user:
        raise ValueError("Could not retrieve Twitter user info")

    account = crud.upsert_platform_account(
        session=session,
        integration=integration,
        external_id=user["id"],
        name=user.get("name", user["id"]),
        avatar_url=user.get("profile_image_url"),
        account_type="user",
    )
    if public_metrics := user.get("public_metrics"):
        _sync_account_snapshot(session, account.id, public_metrics)
    with log_http_errors(f"Twitter tweets for user {user['id']}"):
        _sync_tweets(session, account.id, user["id"], access_token)
