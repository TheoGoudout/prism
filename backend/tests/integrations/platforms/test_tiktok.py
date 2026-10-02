"""
Tests for the TikTok sync module.
All HTTP calls are mocked — no real TikTok API calls.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx

from app.integrations.platforms import SYNC_FUNCTIONS
from app.integrations.platforms.tiktok import (
    _fetch_user_info,
    _sync_account_snapshot,
    _sync_videos,
    sync_tiktok,
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
    integ.platform = Platform.tiktok
    integ.external_account_id = "open-id-123"
    return integ


def _make_account() -> MagicMock:
    acc = MagicMock()
    acc.id = uuid.uuid4()
    return acc


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_tiktok_registered_in_sync_registry():
    assert SYNC_FUNCTIONS[Platform.tiktok] is sync_tiktok


# ---------------------------------------------------------------------------
# _fetch_user_info
# ---------------------------------------------------------------------------


@patch("httpx.get")
def test_fetch_user_info_returns_data(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "data": {
                "user": {
                    "open_id": "oid-1",
                    "display_name": "Cool Creator",
                    "follower_count": 50000,
                    "video_count": 120,
                }
            }
        },
    )
    mock_get.return_value.raise_for_status = MagicMock()

    info = _fetch_user_info("token")
    assert mock_get.call_args.kwargs["params"]["fields"].startswith("open_id,")
    assert info["open_id"] == "oid-1"
    assert info["follower_count"] == 50000


# ---------------------------------------------------------------------------
# _sync_account_snapshot
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.tiktok.crud")
def test_sync_account_snapshot_upserts(mock_crud):
    user_info = {"follower_count": 10000, "video_count": 80}
    _sync_account_snapshot(MagicMock(), uuid.uuid4(), user_info)

    mock_crud.upsert_metric_snapshot.assert_called_once()
    snap = mock_crud.upsert_metric_snapshot.call_args.kwargs["snapshot_in"]
    assert snap.followers_count == 10000
    assert snap.posts_count == 80


# ---------------------------------------------------------------------------
# _sync_videos
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.tiktok.crud")
@patch("httpx.post")
def test_sync_videos_upserts_recent_videos(mock_post, mock_crud):
    recent_ts = int((datetime.now(UTC) - timedelta(days=5)).timestamp())
    videos_resp = {
        "data": {
            "videos": [
                {
                    "id": "vid-1",
                    "video_description": "My video",
                    "create_time": recent_ts,
                    "share_url": "https://tiktok.com/vid/1",
                    "cover_image_url": "https://cdn.tiktok/cover.jpg",
                    "view_count": 100000,
                    "like_count": 5000,
                    "comment_count": 300,
                    "share_count": 200,
                }
            ]
        }
    }
    mock_post.return_value = MagicMock(status_code=200, json=lambda: videos_resp)
    mock_post.return_value.raise_for_status = MagicMock()

    _sync_videos(MagicMock(), uuid.uuid4(), "token")

    # Fields go in the query string, options in the JSON body
    assert "view_count" in mock_post.call_args.kwargs["params"]["fields"]
    assert mock_post.call_args.kwargs["json"] == {"max_count": 20}
    mock_crud.upsert_post.assert_called_once()
    post = mock_crud.upsert_post.call_args.kwargs["post_in"]
    assert post.external_id == "vid-1"
    assert post.content_type == ContentType.video
    assert post.views == 100000
    assert post.likes == 5000
    assert post.engagements == 5000 + 300 + 200


@patch("app.integrations.platforms.tiktok.crud")
@patch("httpx.post")
def test_sync_videos_skips_old_videos(mock_post, mock_crud):
    old_ts = int((datetime.now(UTC) - timedelta(days=35)).timestamp())
    videos_resp = {"data": {"videos": [{"id": "old-vid", "create_time": old_ts}]}}
    mock_post.return_value = MagicMock(status_code=200, json=lambda: videos_resp)
    mock_post.return_value.raise_for_status = MagicMock()

    _sync_videos(MagicMock(), uuid.uuid4(), "token")

    mock_crud.upsert_post.assert_not_called()


@patch("app.integrations.platforms.tiktok.crud")
@patch("httpx.post")
def test_sync_videos_empty(mock_post, mock_crud):
    mock_post.return_value = MagicMock(
        status_code=200, json=lambda: {"data": {"videos": []}}
    )
    mock_post.return_value.raise_for_status = MagicMock()

    _sync_videos(MagicMock(), uuid.uuid4(), "token")
    mock_crud.upsert_post.assert_not_called()


# ---------------------------------------------------------------------------
# sync_tiktok (top-level)
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.tiktok._sync_videos")
@patch("app.integrations.platforms.tiktok._sync_account_snapshot")
@patch("app.integrations.platforms.tiktok.crud")
def test_sync_tiktok_upserts_account_and_calls_sub_syncs(
    mock_crud, mock_snapshot, mock_videos
):
    integ = _make_integration()
    mock_crud.upsert_platform_account.return_value = _make_account()

    user_info = {
        "open_id": "oid-1",
        "display_name": "Creator",
        "follower_count": 5000,
        "video_count": 40,
    }
    with patch(
        "app.integrations.platforms.tiktok._fetch_user_info", return_value=user_info
    ):
        sync_tiktok(MagicMock(), integ, "token")

    mock_crud.upsert_platform_account.assert_called_once()
    mock_snapshot.assert_called_once()
    mock_videos.assert_called_once()


@patch("app.integrations.platforms.tiktok._sync_videos")
@patch("app.integrations.platforms.tiktok._sync_account_snapshot")
@patch("app.integrations.platforms.tiktok.crud")
def test_sync_tiktok_video_error_does_not_raise(mock_crud, mock_snapshot, mock_videos):
    integ = _make_integration()
    mock_crud.upsert_platform_account.return_value = _make_account()
    mock_videos.side_effect = httpx.HTTPStatusError(
        "429", request=MagicMock(), response=MagicMock(status_code=429)
    )

    user_info = {"open_id": "oid-1", "display_name": "X", "follower_count": 100}
    with patch(
        "app.integrations.platforms.tiktok._fetch_user_info", return_value=user_info
    ):
        sync_tiktok(MagicMock(), integ, "token")  # should not raise

    mock_snapshot.assert_called_once()
