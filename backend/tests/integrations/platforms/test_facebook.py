"""
Tests for the Facebook Pages sync module.
All HTTP calls are mocked with unittest.mock — no real Graph API calls.
"""
import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from app.integrations.platforms.facebook import (
    _fetch_managed_pages,
    _sync_page_insights,
    _sync_page_posts,
    sync_facebook,
)
from app.models.integration import Platform
from app.worker.tasks.sync import _platform_sync


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_integration(access_token: str = "user-token-abc") -> MagicMock:
    integ = MagicMock()
    integ.id = uuid.uuid4()
    integ.workspace_id = uuid.uuid4()
    integ.platform = Platform.facebook
    return integ


def _make_account(external_id: str = "page-1") -> MagicMock:
    acc = MagicMock()
    acc.id = uuid.uuid4()
    acc.external_id = external_id
    return acc


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_facebook_registered_in_sync_registry():
    """Importing the module should register the sync function."""
    assert _platform_sync.get(Platform.facebook.value) is not None


# ---------------------------------------------------------------------------
# _fetch_managed_pages
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.facebook.httpx.get")
def test_fetch_managed_pages_returns_list(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "data": [
                {"id": "111", "name": "My Page", "access_token": "page-token"},
            ]
        },
    )
    mock_get.return_value.raise_for_status = MagicMock()

    pages = _fetch_managed_pages("user-token")

    assert len(pages) == 1
    assert pages[0]["id"] == "111"
    assert pages[0]["access_token"] == "page-token"


@patch("app.integrations.platforms.facebook.httpx.get")
def test_fetch_managed_pages_empty(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: {"data": []}
    )
    mock_get.return_value.raise_for_status = MagicMock()

    pages = _fetch_managed_pages("user-token")
    assert pages == []


# ---------------------------------------------------------------------------
# _sync_page_insights
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.facebook.crud")
@patch("app.integrations.platforms.facebook.httpx.get")
def test_sync_page_insights_upserts_snapshots(mock_get, mock_crud):
    insight_data = {
        "data": [
            {
                "name": "page_media_view",
                "values": [
                    {"end_time": "2024-01-15T08:00:00+0000", "value": 500},
                    {"end_time": "2024-01-16T08:00:00+0000", "value": 600},
                ],
            },
            {
                "name": "page_total_media_view_unique",
                "values": [
                    {"end_time": "2024-01-15T08:00:00+0000", "value": 300},
                    {"end_time": "2024-01-16T08:00:00+0000", "value": 350},
                ],
            },
            {
                "name": "page_follows",
                "values": [
                    {"end_time": "2024-01-15T08:00:00+0000", "value": 1000},
                    {"end_time": "2024-01-16T08:00:00+0000", "value": 1010},
                ],
            },
        ]
    }
    mock_get.return_value = MagicMock(status_code=200, json=lambda: insight_data)
    mock_get.return_value.raise_for_status = MagicMock()

    session = MagicMock()
    account_id = uuid.uuid4()

    _sync_page_insights(session, account_id, "page-111", "page-token")

    # Two distinct dates → two upsert calls
    assert mock_crud.upsert_metric_snapshot.call_count == 2
    call_args_list = mock_crud.upsert_metric_snapshot.call_args_list
    dates_seen = {c.kwargs["snapshot_in"].date for c in call_args_list}
    assert date(2024, 1, 15) in dates_seen
    assert date(2024, 1, 16) in dates_seen

    # Spot-check first snapshot
    first = next(c.kwargs["snapshot_in"] for c in call_args_list if c.kwargs["snapshot_in"].date == date(2024, 1, 15))
    assert first.views == 500
    assert first.reach == 300
    assert first.followers_count == 1000


@patch("app.integrations.platforms.facebook.crud")
@patch("app.integrations.platforms.facebook.httpx.get")
def test_sync_page_insights_falls_back_per_metric_on_invalid_metric(mock_get, mock_crud):
    """If Meta rejects one metric, the others are still synced."""

    def _side_effect(url, params, **kwargs):
        metric = params["metric"]
        if "," in metric or metric == "page_follows":
            raise httpx.HTTPStatusError(
                "400", request=MagicMock(), response=MagicMock(status_code=400)
            )
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json.return_value = {
            "data": [
                {
                    "name": metric,
                    "values": [{"end_time": "2024-01-15T08:00:00+0000", "value": 7}],
                }
            ]
        }
        return r

    mock_get.side_effect = _side_effect

    _sync_page_insights(MagicMock(), uuid.uuid4(), "page-111", "page-token")

    snap = mock_crud.upsert_metric_snapshot.call_args.kwargs["snapshot_in"]
    assert snap.views == 7
    assert snap.engagements == 7
    assert snap.followers_gained == 7
    assert snap.followers_count is None


@patch("app.integrations.platforms.facebook.crud")
@patch("app.integrations.platforms.facebook.httpx.get")
def test_sync_page_insights_server_error_propagates(mock_get, mock_crud):
    mock_get.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock(status_code=500)
    )
    with pytest.raises(httpx.HTTPStatusError):
        _sync_page_insights(MagicMock(), uuid.uuid4(), "page-111", "page-token")


@patch("app.integrations.platforms.facebook.crud")
@patch("app.integrations.platforms.facebook.httpx.get")
def test_sync_page_insights_empty_response(mock_get, mock_crud):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"data": []})
    mock_get.return_value.raise_for_status = MagicMock()

    _sync_page_insights(MagicMock(), uuid.uuid4(), "page-111", "page-token")

    mock_crud.upsert_metric_snapshot.assert_not_called()


# ---------------------------------------------------------------------------
# _sync_page_posts
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.facebook.crud")
@patch("app.integrations.platforms.facebook.httpx.get")
def test_sync_page_posts_upserts_posts(mock_get, mock_crud):
    posts_resp = {
        "data": [
            {
                "id": "post-1",
                "message": "Hello world",
                "created_time": "2024-01-15T12:00:00+0000",
                "permalink_url": "https://fb.com/post-1",
                "full_picture": "https://cdn.fb.com/img.jpg",
                "shares": {"count": 4},
                "comments": {"data": [], "summary": {"total_count": 6}},
            }
        ]
    }
    insights_resp = {
        "data": [
            {"name": "post_media_view", "values": [{"value": 1000, "end_time": "x"}]},
            {"name": "post_total_media_view_unique", "values": [{"value": 600, "end_time": "x"}]},
            {"name": "post_reactions_like_total", "values": [{"value": 30, "end_time": "x"}]},
            {"name": "post_clicks", "values": [{"value": 20, "end_time": "x"}]},
        ]
    }

    responses = [
        MagicMock(status_code=200, json=lambda r=posts_resp: r),
        MagicMock(status_code=200, json=lambda r=insights_resp: r),
    ]
    for r in responses:
        r.raise_for_status = MagicMock()
    mock_get.side_effect = responses

    session = MagicMock()
    account_id = uuid.uuid4()

    _sync_page_posts(session, account_id, "page-111", "page-token")

    mock_crud.upsert_post.assert_called_once()
    post_in = mock_crud.upsert_post.call_args.kwargs["post_in"]
    assert post_in.external_id == "post-1"
    assert post_in.views == 1000
    assert post_in.reach == 600
    assert post_in.likes == 30
    assert post_in.comments == 6
    assert post_in.shares == 4
    assert post_in.engagements == 40  # likes + comments + shares
    assert post_in.clicks == 20
    assert post_in.text == "Hello world"


@patch("app.integrations.platforms.facebook.crud")
@patch("app.integrations.platforms.facebook.httpx.get")
def test_sync_page_posts_insight_error_skips_gracefully(mock_get, mock_crud):
    """Post insights failure should not abort the whole post sync."""
    posts_resp = {
        "data": [
            {
                "id": "post-2",
                "message": "Test",
                "created_time": "2024-01-16T10:00:00+0000",
            }
        ]
    }

    def _side_effect(url, **kwargs):
        if "insights" in url:
            raise httpx.HTTPStatusError(
                "403", request=MagicMock(), response=MagicMock(status_code=403)
            )
        r = MagicMock(status_code=200, json=lambda: posts_resp)
        r.raise_for_status = MagicMock()
        return r

    mock_get.side_effect = _side_effect

    _sync_page_posts(MagicMock(), uuid.uuid4(), "page-111", "page-token")

    # Post should still be upserted even without insights
    mock_crud.upsert_post.assert_called_once()
    post_in = mock_crud.upsert_post.call_args.kwargs["post_in"]
    assert post_in.views is None
    assert post_in.engagements is None


@patch("app.integrations.platforms.facebook.crud")
@patch("app.integrations.platforms.facebook.httpx.get")
def test_sync_page_posts_no_posts(mock_get, mock_crud):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"data": []})
    mock_get.return_value.raise_for_status = MagicMock()

    _sync_page_posts(MagicMock(), uuid.uuid4(), "page-111", "page-token")

    mock_crud.upsert_post.assert_not_called()


# ---------------------------------------------------------------------------
# sync_facebook (top-level)
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.facebook._sync_page_posts")
@patch("app.integrations.platforms.facebook._sync_page_insights")
@patch("app.integrations.platforms.facebook.crud")
def test_sync_facebook_upserts_accounts_and_calls_sub_syncs(
    mock_crud, mock_insights, mock_posts
):
    integ = _make_integration()
    mock_crud.get_access_token.return_value = "user-token"

    pages = [
        {"id": "page-A", "name": "Page A", "access_token": "tok-A"},
        {"id": "page-B", "name": "Page B", "access_token": "tok-B"},
    ]
    account_a = _make_account("page-A")
    account_b = _make_account("page-B")
    mock_crud.upsert_platform_account.side_effect = [account_a, account_b]

    with patch(
        "app.integrations.platforms.facebook._fetch_managed_pages", return_value=pages
    ):
        sync_facebook(MagicMock(), integ)

    assert mock_crud.upsert_platform_account.call_count == 2
    assert mock_insights.call_count == 2
    assert mock_posts.call_count == 2


@patch("app.integrations.platforms.facebook.crud")
def test_sync_facebook_no_access_token_raises(mock_crud):
    integ = _make_integration()
    mock_crud.get_access_token.return_value = None

    with pytest.raises(ValueError, match="No access token"):
        sync_facebook(MagicMock(), integ)


@patch("app.integrations.platforms.facebook._fetch_managed_pages", return_value=[])
@patch("app.integrations.platforms.facebook.crud")
def test_sync_facebook_no_pages_is_noop(mock_crud, _mock_pages):
    integ = _make_integration()
    mock_crud.get_access_token.return_value = "user-token"

    sync_facebook(MagicMock(), integ)  # should not raise

    mock_crud.upsert_platform_account.assert_not_called()


@patch("app.integrations.platforms.facebook._sync_page_posts")
@patch("app.integrations.platforms.facebook._sync_page_insights")
@patch("app.integrations.platforms.facebook.crud")
def test_sync_facebook_insights_error_continues_to_posts(
    mock_crud, mock_insights, mock_posts
):
    """An HTTP error in page insights should not abort post sync."""
    integ = _make_integration()
    mock_crud.get_access_token.return_value = "user-token"
    mock_crud.upsert_platform_account.return_value = _make_account()

    mock_insights.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock(status_code=500)
    )

    with patch(
        "app.integrations.platforms.facebook._fetch_managed_pages",
        return_value=[{"id": "page-X", "name": "X", "access_token": "tok"}],
    ):
        sync_facebook(MagicMock(), integ)  # should not raise

    mock_posts.assert_called_once()
