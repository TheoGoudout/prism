"""
Tests for the Instagram Business sync module.
All HTTP calls are mocked — no real Graph API calls.
"""

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import httpx

from app.integrations.platforms import SYNC_FUNCTIONS
from app.integrations.platforms.instagram import (
    _fetch_instagram_accounts,
    _sync_account_insights,
    _sync_media,
    sync_instagram,
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
    integ.platform = Platform.instagram
    return integ


def _make_account(external_id: str = "ig-123") -> MagicMock:
    acc = MagicMock()
    acc.id = uuid.uuid4()
    acc.external_id = external_id
    return acc


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_instagram_registered_in_sync_registry():
    assert SYNC_FUNCTIONS[Platform.instagram] is sync_instagram


# ---------------------------------------------------------------------------
# _fetch_instagram_accounts
# ---------------------------------------------------------------------------


@patch("httpx.get")
def test_fetch_instagram_accounts_returns_linked_accounts(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "data": [
                {
                    "id": "page-1",
                    "access_token": "page-tok",
                    "instagram_business_account": {
                        "id": "ig-111",
                        "name": "My Brand",
                        "profile_picture_url": "https://cdn/pic.jpg",
                        "username": "mybrand",
                    },
                },
                {
                    "id": "page-2",
                    "access_token": "page-tok-2",
                    # No instagram_business_account — should be skipped
                },
            ]
        },
    )
    mock_get.return_value.raise_for_status = MagicMock()

    accounts = _fetch_instagram_accounts("user-token")

    assert len(accounts) == 1
    assert accounts[0]["ig_id"] == "ig-111"
    assert accounts[0]["name"] == "My Brand"
    assert accounts[0]["page_token"] == "page-tok"


@patch("httpx.get")
def test_fetch_instagram_accounts_empty(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"data": []})
    mock_get.return_value.raise_for_status = MagicMock()

    assert _fetch_instagram_accounts("user-token") == []


# ---------------------------------------------------------------------------
# _sync_account_insights
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.instagram.crud")
@patch("httpx.get")
def test_sync_account_insights_upserts_snapshots(mock_get, mock_crud):
    insight_data = {
        "data": [
            {
                "name": "reach",
                "values": [
                    {"end_time": "2024-02-01T08:00:00+0000", "value": 1500},
                    {"end_time": "2024-02-02T08:00:00+0000", "value": 1800},
                ],
            },
            {
                "name": "follower_count",
                "values": [
                    {"end_time": "2024-02-01T08:00:00+0000", "value": 12},
                    {"end_time": "2024-02-02T08:00:00+0000", "value": 20},
                ],
            },
        ]
    }
    mock_get.return_value = MagicMock(status_code=200, json=lambda: insight_data)
    mock_get.return_value.raise_for_status = MagicMock()

    account_id = uuid.uuid4()
    _sync_account_insights(MagicMock(), account_id, "ig-111", "tok")

    assert mock_crud.upsert_metric_snapshot.call_count == 2
    snapshots = [
        c.kwargs["snapshot_in"] for c in mock_crud.upsert_metric_snapshot.call_args_list
    ]
    dates = {s.date for s in snapshots}
    assert date(2024, 2, 1) in dates
    assert date(2024, 2, 2) in dates

    snap_feb1 = next(s for s in snapshots if s.date == date(2024, 2, 1))
    assert snap_feb1.reach == 1500
    # follower_count is daily *new* followers
    assert snap_feb1.followers_gained == 12
    assert snap_feb1.followers_count is None


@patch("app.integrations.platforms.instagram.crud")
@patch("httpx.get")
def test_sync_account_insights_records_follower_total_today(mock_get, mock_crud):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"data": []})
    mock_get.return_value.raise_for_status = MagicMock()

    _sync_account_insights(MagicMock(), uuid.uuid4(), "ig-111", "tok", 5000)

    snap = mock_crud.upsert_metric_snapshot.call_args.kwargs["snapshot_in"]
    assert snap.date == date.today()
    assert snap.followers_count == 5000


@patch("app.integrations.platforms.instagram.crud")
@patch("httpx.get")
def test_sync_account_insights_empty(mock_get, mock_crud):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"data": []})
    mock_get.return_value.raise_for_status = MagicMock()

    _sync_account_insights(MagicMock(), uuid.uuid4(), "ig-111", "tok")
    mock_crud.upsert_metric_snapshot.assert_not_called()


# ---------------------------------------------------------------------------
# _sync_media
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.instagram.crud")
@patch("httpx.get")
def test_sync_media_upserts_posts(mock_get, mock_crud):
    media_resp = {
        "data": [
            {
                "id": "media-1",
                "media_type": "IMAGE",
                "timestamp": "2024-02-10T12:00:00+0000",
                "caption": "Nice photo",
                "permalink": "https://instagram.com/p/abc",
                "media_url": "https://cdn.ig/img.jpg",
            }
        ]
    }
    insights_resp = {
        "data": [
            {"name": "views", "values": [{"value": 3000}]},
            {"name": "reach", "values": [{"value": 2500}]},
            {"name": "total_interactions", "values": [{"value": 150}]},
            {"name": "likes", "values": [{"value": 120}]},
            {"name": "comments", "values": [{"value": 30}]},
            {"name": "saved", "values": [{"value": 40}]},
        ]
    }

    responses = [
        MagicMock(status_code=200, json=lambda r=media_resp: r),
        MagicMock(status_code=200, json=lambda r=insights_resp: r),
    ]
    for r in responses:
        r.raise_for_status = MagicMock()
    mock_get.side_effect = responses

    _sync_media(MagicMock(), uuid.uuid4(), "ig-111", "tok")

    mock_crud.upsert_post.assert_called_once()
    post_in = mock_crud.upsert_post.call_args.kwargs["post_in"]
    assert post_in.external_id == "media-1"
    assert post_in.content_type == ContentType.post
    assert post_in.views == 3000
    assert post_in.reach == 2500
    assert post_in.engagements == 150
    assert post_in.likes == 120
    assert post_in.saves == 40
    assert post_in.text == "Nice photo"


@patch("app.integrations.platforms.instagram.crud")
@patch("httpx.get")
def test_sync_media_reel_content_type(mock_get, mock_crud):
    media_resp = {
        "data": [
            {
                "id": "reel-1",
                "media_type": "REEL",
                "timestamp": "2024-02-11T10:00:00+0000",
            }
        ]
    }
    insights_resp = {"data": []}

    responses = [
        MagicMock(status_code=200, json=lambda r=media_resp: r),
        MagicMock(status_code=200, json=lambda r=insights_resp: r),
    ]
    for r in responses:
        r.raise_for_status = MagicMock()
    mock_get.side_effect = responses

    _sync_media(MagicMock(), uuid.uuid4(), "ig-111", "tok")

    post_in = mock_crud.upsert_post.call_args.kwargs["post_in"]
    assert post_in.content_type == ContentType.reel


@patch("app.integrations.platforms.instagram.crud")
@patch("httpx.get")
def test_sync_media_insights_error_still_upserts(mock_get, mock_crud):
    """Media insights failure should not skip the post upsert."""
    media_resp = {
        "data": [
            {
                "id": "media-2",
                "media_type": "IMAGE",
                "timestamp": "2024-02-12T09:00:00+0000",
            }
        ]
    }

    call_count = 0

    def _side_effect(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:  # insights call
            raise httpx.HTTPStatusError(
                "403", request=MagicMock(), response=MagicMock(status_code=403)
            )
        r = MagicMock(status_code=200, json=lambda: media_resp)
        r.raise_for_status = MagicMock()
        return r

    mock_get.side_effect = _side_effect

    _sync_media(MagicMock(), uuid.uuid4(), "ig-111", "tok")

    mock_crud.upsert_post.assert_called_once()
    assert mock_crud.upsert_post.call_args.kwargs["post_in"].views is None


# ---------------------------------------------------------------------------
# sync_instagram (top-level)
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.instagram._sync_media")
@patch("app.integrations.platforms.instagram._sync_account_insights")
@patch("app.integrations.platforms.instagram.crud")
def test_sync_instagram_processes_all_accounts(mock_crud, mock_insights, mock_media):
    integ = _make_integration()

    ig_accounts = [
        {"ig_id": "ig-A", "name": "Brand A", "avatar_url": None, "page_token": "tok-A"},
        {"ig_id": "ig-B", "name": "Brand B", "avatar_url": None, "page_token": "tok-B"},
    ]
    mock_crud.upsert_platform_account.side_effect = [
        _make_account("ig-A"),
        _make_account("ig-B"),
    ]

    with patch(
        "app.integrations.platforms.instagram._fetch_instagram_accounts",
        return_value=ig_accounts,
    ):
        sync_instagram(MagicMock(), integ, "token")

    assert mock_crud.upsert_platform_account.call_count == 2
    assert mock_insights.call_count == 2
    assert mock_media.call_count == 2


@patch(
    "app.integrations.platforms.instagram._fetch_instagram_accounts", return_value=[]
)
@patch("app.integrations.platforms.instagram.crud")
def test_sync_instagram_no_accounts_is_noop(mock_crud, _):
    integ = _make_integration()

    sync_instagram(MagicMock(), integ, "token")

    mock_crud.upsert_platform_account.assert_not_called()


@patch("app.integrations.platforms.instagram._sync_media")
@patch("app.integrations.platforms.instagram._sync_account_insights")
@patch("app.integrations.platforms.instagram.crud")
def test_sync_instagram_insights_error_continues_to_media(
    mock_crud, mock_insights, mock_media
):
    integ = _make_integration()
    mock_crud.upsert_platform_account.return_value = _make_account()
    mock_insights.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock(status_code=500)
    )

    with patch(
        "app.integrations.platforms.instagram._fetch_instagram_accounts",
        return_value=[
            {"ig_id": "ig-X", "name": "X", "avatar_url": None, "page_token": "tok"}
        ],
    ):
        sync_instagram(MagicMock(), integ, "token")

    mock_media.assert_called_once()
