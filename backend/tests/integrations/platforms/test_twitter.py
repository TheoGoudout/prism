"""
Tests for the Twitter/X sync module.
All HTTP calls are mocked — no real Twitter API calls.
"""

import uuid
from unittest.mock import MagicMock, patch

import httpx

from app.integrations.platforms import SYNC_FUNCTIONS
from app.integrations.platforms.twitter import (
    _fetch_user_info,
    _sync_account_snapshot,
    _sync_tweets,
    sync_twitter,
)
from app.models.integration import Platform
from app.models.metrics import ContentType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_integration() -> MagicMock:
    integ = MagicMock()
    integ.id = uuid.uuid4()
    integ.workspace_id = uuid.uuid4()
    integ.platform = Platform.twitter
    return integ


def _make_account() -> MagicMock:
    acc = MagicMock()
    acc.id = uuid.uuid4()
    return acc


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_twitter_registered_in_sync_registry():
    assert SYNC_FUNCTIONS[Platform.twitter] is sync_twitter


# ---------------------------------------------------------------------------
# _fetch_user_info
# ---------------------------------------------------------------------------


@patch("httpx.get")
def test_fetch_user_info_returns_data(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "data": {
                "id": "123",
                "name": "Test User",
                "username": "testuser",
                "public_metrics": {"followers_count": 500, "tweet_count": 200},
            }
        },
    )
    mock_get.return_value.raise_for_status = MagicMock()

    user = _fetch_user_info("token")
    assert user["id"] == "123"
    assert user["public_metrics"]["followers_count"] == 500


# ---------------------------------------------------------------------------
# _sync_account_snapshot
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.twitter.crud")
def test_sync_account_snapshot_upserts(mock_crud):
    account_id = uuid.uuid4()
    public_metrics = {"followers_count": 1000, "tweet_count": 500}

    _sync_account_snapshot(MagicMock(), account_id, public_metrics)

    mock_crud.upsert_metric_snapshot.assert_called_once()
    snap = mock_crud.upsert_metric_snapshot.call_args.kwargs["snapshot_in"]
    assert snap.followers_count == 1000
    assert snap.posts_count == 500


# ---------------------------------------------------------------------------
# _sync_tweets
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.twitter.crud")
@patch("httpx.get")
def test_sync_tweets_upserts_owned_tweets(mock_get, mock_crud):
    tweets_resp = {
        "data": [
            {
                "id": "tweet-1",
                "text": "Hello Twitter",
                "created_at": "2024-03-01T12:00:00Z",
                "public_metrics": {
                    "impression_count": 5000,
                    "like_count": 200,
                    "retweet_count": 50,
                    "reply_count": 30,
                    "quote_count": 10,
                },
            }
        ]
    }
    mock_get.return_value = MagicMock(status_code=200, json=lambda: tweets_resp)
    mock_get.return_value.raise_for_status = MagicMock()

    _sync_tweets(MagicMock(), uuid.uuid4(), "user-123", "token")

    mock_crud.upsert_post.assert_called_once()
    post = mock_crud.upsert_post.call_args.kwargs["post_in"]
    assert post.external_id == "tweet-1"
    assert post.content_type == ContentType.tweet
    assert post.impressions == 5000
    assert post.likes == 200
    assert post.shares == 50
    assert post.comments == 30
    # engagements = likes + retweets + replies + quotes
    assert post.engagements == 200 + 50 + 30 + 10


@patch("app.integrations.platforms.twitter.crud")
@patch("httpx.get")
def test_sync_tweets_skips_retweets(mock_get, mock_crud):
    tweets_resp = {
        "data": [
            {
                "id": "tweet-rt",
                "text": "RT @other: Some content",
                "created_at": "2024-03-02T10:00:00Z",
                "public_metrics": {},
                "referenced_tweets": [{"type": "retweeted", "id": "other-tweet"}],
            }
        ]
    }
    mock_get.return_value = MagicMock(status_code=200, json=lambda: tweets_resp)
    mock_get.return_value.raise_for_status = MagicMock()

    _sync_tweets(MagicMock(), uuid.uuid4(), "user-123", "token")

    mock_crud.upsert_post.assert_not_called()


@patch("app.integrations.platforms.twitter.crud")
@patch("httpx.get")
def test_sync_tweets_empty_response(mock_get, mock_crud):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"data": []})
    mock_get.return_value.raise_for_status = MagicMock()

    _sync_tweets(MagicMock(), uuid.uuid4(), "user-123", "token")
    mock_crud.upsert_post.assert_not_called()


@patch("app.integrations.platforms.twitter.crud")
@patch("httpx.get")
def test_sync_tweets_no_data_key(mock_get, mock_crud):
    """API returns no 'data' key when there are no tweets in range."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {})
    mock_get.return_value.raise_for_status = MagicMock()

    _sync_tweets(MagicMock(), uuid.uuid4(), "user-123", "token")
    mock_crud.upsert_post.assert_not_called()


# ---------------------------------------------------------------------------
# sync_twitter (top-level)
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.twitter._sync_tweets")
@patch("app.integrations.platforms.twitter._sync_account_snapshot")
@patch("app.integrations.platforms.twitter.crud")
def test_sync_twitter_upserts_account_and_calls_sub_syncs(
    mock_crud, mock_snapshot, mock_tweets
):
    integ = _make_integration()
    mock_crud.upsert_platform_account.return_value = _make_account()

    user_data = {
        "id": "user-1",
        "name": "Test Brand",
        "profile_image_url": "https://pbs.twimg.com/pic.jpg",
        "public_metrics": {"followers_count": 300, "tweet_count": 100},
    }

    with patch(
        "app.integrations.platforms.twitter._fetch_user_info", return_value=user_data
    ):
        sync_twitter(MagicMock(), integ, "token")

    mock_crud.upsert_platform_account.assert_called_once()
    mock_snapshot.assert_called_once()
    mock_tweets.assert_called_once()


@patch("app.integrations.platforms.twitter._sync_tweets")
@patch("app.integrations.platforms.twitter._sync_account_snapshot")
@patch("app.integrations.platforms.twitter.crud")
def test_sync_twitter_tweet_error_does_not_raise(mock_crud, mock_snapshot, mock_tweets):
    integ = _make_integration()
    mock_crud.upsert_platform_account.return_value = _make_account()
    mock_tweets.side_effect = httpx.HTTPStatusError(
        "429", request=MagicMock(), response=MagicMock(status_code=429)
    )

    user_data = {
        "id": "user-1",
        "name": "Brand",
        "public_metrics": {"followers_count": 100, "tweet_count": 50},
    }
    with patch(
        "app.integrations.platforms.twitter._fetch_user_info", return_value=user_data
    ):
        sync_twitter(MagicMock(), integ, "token")  # should not raise

    mock_snapshot.assert_called_once()
