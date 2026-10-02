"""
Tests for the LinkedIn sync module.
All HTTP calls are mocked — no real LinkedIn API calls.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx

from app.integrations.platforms import SYNC_FUNCTIONS
from app.integrations.platforms.linkedin import (
    _fetch_admin_organizations,
    _sync_follower_stats,
    _sync_org_posts,
    sync_linkedin,
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
    integ.platform = Platform.linkedin
    return integ


def _make_account() -> MagicMock:
    acc = MagicMock()
    acc.id = uuid.uuid4()
    return acc


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_linkedin_registered_in_sync_registry():
    assert SYNC_FUNCTIONS[Platform.linkedin] is sync_linkedin


# ---------------------------------------------------------------------------
# _fetch_admin_organizations
# ---------------------------------------------------------------------------


@patch("httpx.get")
def test_fetch_admin_orgs_returns_orgs(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "elements": [
                {
                    "organization": "urn:li:organization:12345",
                    "organization~": {
                        "localizedName": "Acme Corp",
                        "logoV2": {},
                    },
                }
            ]
        },
    )
    mock_get.return_value.raise_for_status = MagicMock()

    orgs = _fetch_admin_organizations("token")
    assert len(orgs) == 1
    assert orgs[0]["org_id"] == "12345"
    assert orgs[0]["name"] == "Acme Corp"
    assert orgs[0]["org_urn"] == "urn:li:organization:12345"


@patch("httpx.get")
def test_fetch_admin_orgs_empty(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"elements": []})
    mock_get.return_value.raise_for_status = MagicMock()

    assert _fetch_admin_organizations("token") == []


# ---------------------------------------------------------------------------
# _sync_follower_stats
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.linkedin.crud")
@patch("httpx.get")
def test_sync_follower_stats_upserts_snapshot(mock_get, mock_crud):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"firstDegreeSize": 2500},
    )
    mock_get.return_value.raise_for_status = MagicMock()

    _sync_follower_stats(MagicMock(), uuid.uuid4(), "12345", "token")

    mock_crud.upsert_metric_snapshot.assert_called_once()
    snap = mock_crud.upsert_metric_snapshot.call_args.kwargs["snapshot_in"]
    assert snap.followers_count == 2500


# ---------------------------------------------------------------------------
# _sync_org_posts
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.linkedin.crud")
@patch("httpx.get")
def test_sync_org_posts_upserts_posts(mock_get, mock_crud):
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    shares_resp = {
        "elements": [
            {
                "id": "share-1",
                "created": {"time": now_ms - 86400000},  # 1 day ago
                "text": {"text": "Great update!"},
            }
        ]
    }
    stats_resp = {
        "elements": [
            {
                "totalShareStatistics": {
                    "impressionCount": 5000,
                    "uniqueImpressionsCount": 3000,
                    "likeCount": 120,
                    "commentCount": 30,
                    "shareCount": 15,
                    "clickCount": 200,
                    "engagement": 0.073,  # a rate, not a count
                }
            }
        ]
    }

    responses = [
        MagicMock(status_code=200, json=lambda r=shares_resp: r),
        MagicMock(status_code=200, json=lambda r=stats_resp: r),
    ]
    for r in responses:
        r.raise_for_status = MagicMock()
    mock_get.side_effect = responses

    _sync_org_posts(MagicMock(), uuid.uuid4(), "urn:li:organization:12345", "token")

    mock_crud.upsert_post.assert_called_once()
    post = mock_crud.upsert_post.call_args.kwargs["post_in"]
    assert post.external_id == "share-1"
    assert post.content_type == ContentType.article
    assert post.impressions == 5000
    assert post.reach == 3000
    assert post.likes == 120
    assert post.engagements == 120 + 30 + 15 + 200
    assert post.raw_data["engagement"] == 0.073
    assert post.text == "Great update!"


@patch("app.integrations.platforms.linkedin.crud")
@patch("httpx.get")
def test_sync_org_posts_stats_error_still_upserts(mock_get, mock_crud):
    """Statistics fetch failure should not skip the post upsert."""
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    shares_resp = {
        "elements": [{"id": "share-2", "created": {"time": now_ms - 3600000}}]
    }

    call_count = 0

    def _side_effect(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise httpx.HTTPStatusError(
                "403", request=MagicMock(), response=MagicMock(status_code=403)
            )
        r = MagicMock(status_code=200, json=lambda: shares_resp)
        r.raise_for_status = MagicMock()
        return r

    mock_get.side_effect = _side_effect

    _sync_org_posts(MagicMock(), uuid.uuid4(), "urn:li:organization:12345", "token")

    mock_crud.upsert_post.assert_called_once()
    assert mock_crud.upsert_post.call_args.kwargs["post_in"].impressions is None


@patch("app.integrations.platforms.linkedin.crud")
@patch("httpx.get")
def test_sync_org_posts_skips_old_shares(mock_get, mock_crud):
    """Shares older than 30 days should be skipped."""
    old_ms = int((datetime.now(UTC).timestamp() - 35 * 86400) * 1000)
    shares_resp = {"elements": [{"id": "old-share", "created": {"time": old_ms}}]}
    mock_get.return_value = MagicMock(status_code=200, json=lambda: shares_resp)
    mock_get.return_value.raise_for_status = MagicMock()

    _sync_org_posts(MagicMock(), uuid.uuid4(), "urn:li:organization:12345", "token")

    mock_crud.upsert_post.assert_not_called()


# ---------------------------------------------------------------------------
# sync_linkedin (top-level)
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.linkedin._sync_org_posts")
@patch("app.integrations.platforms.linkedin._sync_follower_stats")
@patch("app.integrations.platforms.linkedin.crud")
def test_sync_linkedin_processes_all_orgs(mock_crud, mock_followers, mock_posts):
    integ = _make_integration()

    orgs = [
        {
            "org_id": "1",
            "org_urn": "urn:li:organization:1",
            "name": "Org A",
            "avatar_url": None,
        },
        {
            "org_id": "2",
            "org_urn": "urn:li:organization:2",
            "name": "Org B",
            "avatar_url": None,
        },
    ]
    mock_crud.upsert_platform_account.side_effect = [_make_account(), _make_account()]

    with patch(
        "app.integrations.platforms.linkedin._fetch_admin_organizations",
        return_value=orgs,
    ):
        sync_linkedin(MagicMock(), integ, "token")

    assert mock_crud.upsert_platform_account.call_count == 2
    assert mock_followers.call_count == 2
    assert mock_posts.call_count == 2


@patch(
    "app.integrations.platforms.linkedin._fetch_admin_organizations", return_value=[]
)
@patch("app.integrations.platforms.linkedin.crud")
def test_sync_linkedin_no_orgs_is_noop(mock_crud, _):
    integ = _make_integration()

    sync_linkedin(MagicMock(), integ, "token")
    mock_crud.upsert_platform_account.assert_not_called()
