"""
Tests for the Google Analytics 4 sync module.
All HTTP calls are mocked — no real GA4 API calls.
"""

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import httpx

from app.integrations.platforms import SYNC_FUNCTIONS
from app.integrations.platforms.google_analytics import (
    _fetch_ga4_properties,
    _sync_property_report,
    sync_google_analytics,
)
from app.models.integration import Platform

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_integration() -> MagicMock:
    integ = MagicMock()
    integ.id = uuid.uuid4()
    integ.workspace_id = uuid.uuid4()
    integ.platform = Platform.google_analytics
    return integ


def _make_account() -> MagicMock:
    acc = MagicMock()
    acc.id = uuid.uuid4()
    return acc


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_google_analytics_registered_in_sync_registry():
    assert SYNC_FUNCTIONS[Platform.google_analytics] is sync_google_analytics


# ---------------------------------------------------------------------------
# _fetch_ga4_properties
# ---------------------------------------------------------------------------


@patch("httpx.get")
def test_fetch_ga4_properties_returns_list(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "properties": [
                {"name": "properties/123456789", "displayName": "My Website"},
                {"name": "properties/987654321", "displayName": "Blog"},
            ]
        },
    )
    mock_get.return_value.raise_for_status = MagicMock()

    props = _fetch_ga4_properties("token")

    assert len(props) == 2
    assert props[0]["property_id"] == "123456789"
    assert props[0]["display_name"] == "My Website"
    assert props[1]["property_id"] == "987654321"


@patch("httpx.get")
def test_fetch_ga4_properties_empty(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"properties": []})
    mock_get.return_value.raise_for_status = MagicMock()

    assert _fetch_ga4_properties("token") == []


# ---------------------------------------------------------------------------
# _sync_property_report
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.google_analytics.crud")
@patch("httpx.post")
def test_sync_property_report_upserts_daily_snapshots(mock_post, mock_crud):
    report_resp = {
        "dimensionHeaders": [{"name": "date"}],
        "metricHeaders": [
            {"name": "sessions"},
            {"name": "engagedSessions"},
            {"name": "totalUsers"},
            {"name": "screenPageViews"},
            {"name": "bounceRate"},
            {"name": "conversions"},
            {"name": "engagementRate"},
        ],
        "rows": [
            {
                "dimensionValues": [{"value": "20240301"}],
                "metricValues": [
                    {"value": "1200"},
                    {"value": "700"},
                    {"value": "900"},
                    {"value": "3500"},
                    {"value": "0.42"},
                    {"value": "80"},
                    {"value": "0.58"},
                ],
            },
            {
                "dimensionValues": [{"value": "20240302"}],
                "metricValues": [
                    {"value": "1350"},
                    {"value": "800"},
                    {"value": "1000"},
                    {"value": "4000"},
                    {"value": "0.38"},
                    {"value": "95"},
                    {"value": "0.62"},
                ],
            },
        ],
    }
    mock_post.return_value = MagicMock(status_code=200, json=lambda: report_resp)
    mock_post.return_value.raise_for_status = MagicMock()

    account_id = uuid.uuid4()
    _sync_property_report(MagicMock(), account_id, "properties/123", "token")

    assert mock_crud.upsert_metric_snapshot.call_count == 2
    snapshots = [
        c.kwargs["snapshot_in"] for c in mock_crud.upsert_metric_snapshot.call_args_list
    ]
    dates = {s.date for s in snapshots}
    assert date(2024, 3, 1) in dates
    assert date(2024, 3, 2) in dates

    snap_mar1 = next(s for s in snapshots if s.date == date(2024, 3, 1))
    assert snap_mar1.impressions == 1200  # sessions → impressions
    assert snap_mar1.reach == 900  # totalUsers → reach
    assert snap_mar1.engagements == 700  # engagedSessions → engagements
    assert snap_mar1.views == 3500  # screenPageViews → views
    assert snap_mar1.clicks == 80  # conversions → clicks
    assert snap_mar1.raw_data["bounceRate"] == 0.42


@patch("app.integrations.platforms.google_analytics.crud")
@patch("httpx.post")
def test_sync_property_report_empty_rows(mock_post, mock_crud):
    report_resp = {
        "dimensionHeaders": [{"name": "date"}],
        "metricHeaders": [{"name": "sessions"}],
        "rows": [],
    }
    mock_post.return_value = MagicMock(status_code=200, json=lambda: report_resp)
    mock_post.return_value.raise_for_status = MagicMock()

    _sync_property_report(MagicMock(), uuid.uuid4(), "properties/123", "token")
    mock_crud.upsert_metric_snapshot.assert_not_called()


# ---------------------------------------------------------------------------
# sync_google_analytics (top-level)
# ---------------------------------------------------------------------------


@patch("app.integrations.platforms.google_analytics._sync_property_report")
@patch("app.integrations.platforms.google_analytics.crud")
def test_sync_ga4_processes_all_properties(mock_crud, mock_report):
    integ = _make_integration()

    properties = [
        {"property_id": "1", "property_name": "properties/1", "display_name": "Site A"},
        {"property_id": "2", "property_name": "properties/2", "display_name": "Site B"},
    ]
    mock_crud.upsert_platform_account.side_effect = [_make_account(), _make_account()]

    with patch(
        "app.integrations.platforms.google_analytics._fetch_ga4_properties",
        return_value=properties,
    ):
        sync_google_analytics(MagicMock(), integ, "token")

    assert mock_crud.upsert_platform_account.call_count == 2
    assert mock_report.call_count == 2


@patch(
    "app.integrations.platforms.google_analytics._fetch_ga4_properties", return_value=[]
)
@patch("app.integrations.platforms.google_analytics.crud")
def test_sync_ga4_no_properties_is_noop(mock_crud, _):
    integ = _make_integration()

    sync_google_analytics(MagicMock(), integ, "token")
    mock_crud.upsert_platform_account.assert_not_called()


@patch("app.integrations.platforms.google_analytics._sync_property_report")
@patch("app.integrations.platforms.google_analytics.crud")
def test_sync_ga4_report_error_continues_to_next_property(mock_crud, mock_report):
    integ = _make_integration()
    mock_crud.upsert_platform_account.side_effect = [_make_account(), _make_account()]

    call_count = 0

    def _report_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.HTTPStatusError(
                "403", request=MagicMock(), response=MagicMock(status_code=403)
            )

    mock_report.side_effect = _report_side_effect

    properties = [
        {"property_id": "1", "property_name": "properties/1", "display_name": "A"},
        {"property_id": "2", "property_name": "properties/2", "display_name": "B"},
    ]
    with patch(
        "app.integrations.platforms.google_analytics._fetch_ga4_properties",
        return_value=properties,
    ):
        sync_google_analytics(MagicMock(), integ, "token")  # should not raise

    assert mock_report.call_count == 2  # both properties attempted
