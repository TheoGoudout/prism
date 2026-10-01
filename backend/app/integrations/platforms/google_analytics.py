"""
Google Analytics 4 (GA4) sync.

Fetches:
  - GA4 properties accessible to the authenticated user → PlatformAccounts
  - 30-day daily report: sessions, users, pageviews, bounce rate, conversions
    (using the GA4 Data API runReport endpoint)

Uses the Google Analytics Data API v1 with the Bearer token.
The token may be short-lived; the sync task should refresh it before calling
(token refresh is handled at the Celery layer via crud.update_integration_tokens).
"""

import logging
from datetime import date, timedelta
from typing import Any

import httpx
from sqlmodel import Session

from app import crud
from app.models.integration import Integration, Platform, PlatformAccountCreate
from app.models.metrics import MetricSnapshotUpsert
from app.worker.tasks.sync import register_platform_sync

logger = logging.getLogger(__name__)

GA_ADMIN_API = "https://analyticsadmin.googleapis.com/v1beta"
GA_DATA_API = "https://analyticsdata.googleapis.com/v1beta"


# ---------------------------------------------------------------------------
# Internal HTTP helpers
# ---------------------------------------------------------------------------


def _get(path: str, token: str, base: str = GA_ADMIN_API) -> dict[str, Any]:
    resp = httpx.get(
        f"{base}/{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    result: dict[str, Any] = resp.json()
    return result


def _post(
    path: str, token: str, body: dict[str, Any], base: str = GA_DATA_API
) -> dict[str, Any]:
    resp = httpx.post(
        f"{base}/{path}",
        json=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    result: dict[str, Any] = resp.json()
    return result


# ---------------------------------------------------------------------------
# Property discovery
# ---------------------------------------------------------------------------


def _fetch_ga4_properties(token: str) -> list[dict[str, Any]]:
    """
    Return GA4 properties accessible to the user.
    Each entry has: property_id, display_name.
    """
    resp = _get("properties", token, base=GA_ADMIN_API)
    properties = []
    for prop in resp.get("properties", []):
        # property name is like "properties/123456789"
        prop_name: str = prop.get("name", "")
        prop_id = prop_name.split("/")[-1] if "/" in prop_name else prop_name
        properties.append(
            {
                "property_id": prop_id,
                "property_name": prop_name,
                "display_name": prop.get("displayName", prop_id),
            }
        )
    return properties


# ---------------------------------------------------------------------------
# Daily report
# ---------------------------------------------------------------------------


def _sync_property_report(
    session: Session,
    platform_account_id: Any,
    property_name: str,
    token: str,
) -> None:
    end = date.today()
    start = end - timedelta(days=30)

    report = _post(
        f"{property_name}:runReport",
        token,
        {
            "dateRanges": [
                {
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                }
            ],
            "dimensions": [{"name": "date"}],
            "metrics": [
                {"name": "sessions"},
                {"name": "totalUsers"},
                {"name": "screenPageViews"},
                {"name": "bounceRate"},
                {"name": "conversions"},
                {"name": "engagementRate"},
            ],
        },
    )

    dimension_headers = [d["name"] for d in report.get("dimensionHeaders", [])]
    metric_headers = [m["name"] for m in report.get("metricHeaders", [])]

    for row in report.get("rows", []):
        dim_vals = row.get("dimensionValues", [])
        met_vals = row.get("metricValues", [])

        # date dimension is formatted as YYYYMMDD
        try:
            date_str = dim_vals[dimension_headers.index("date")]["value"]
            d = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
        except (IndexError, KeyError, ValueError):
            continue

        def _metric(
            name: str, met_vals: list[dict[str, Any]] = met_vals
        ) -> float | None:
            try:
                idx = metric_headers.index(name)
                return float(met_vals[idx]["value"])
            except (IndexError, ValueError, KeyError):
                return None

        sessions = _metric("sessions")
        users = _metric("totalUsers")
        pageviews = _metric("screenPageViews")
        bounce_rate = _metric("bounceRate")
        conversions = _metric("conversions")
        engagement_rate = _metric("engagementRate")

        snapshot = MetricSnapshotUpsert(
            date=d,
            views=int(pageviews) if pageviews is not None else None,
            # Map sessions → impressions (closest analogue in our normalised schema)
            impressions=int(sessions) if sessions is not None else None,
            # Unique users → reach
            reach=int(users) if users is not None else None,
            # Conversions → clicks (closest analogue)
            clicks=int(conversions) if conversions is not None else None,
            raw_data={
                "sessions": sessions,
                "totalUsers": users,
                "screenPageViews": pageviews,
                "bounceRate": bounce_rate,
                "conversions": conversions,
                "engagementRate": engagement_rate,
            },
        )
        crud.upsert_metric_snapshot(
            session=session,
            platform_account_id=platform_account_id,
            snapshot_in=snapshot,
        )


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------


def sync_google_analytics(session: Session, integration: Integration) -> None:
    """Sync all accessible GA4 properties for this integration."""
    token = crud.get_access_token(integration)
    if not token:
        raise ValueError("No access token available for Google Analytics integration")

    properties = _fetch_ga4_properties(token)
    if not properties:
        logger.info(
            "sync_google_analytics: no GA4 properties for integration %s",
            integration.id,
        )
        return

    for prop in properties:
        prop_id: str = prop["property_id"]
        prop_name: str = prop["property_name"]

        account_in = PlatformAccountCreate(
            integration_id=integration.id,
            workspace_id=integration.workspace_id,
            platform=Platform.google_analytics,
            external_id=prop_id,
            name=prop["display_name"],
            avatar_url=None,
            account_type="property",
        )
        account = crud.upsert_platform_account(session=session, account_in=account_in)

        try:
            _sync_property_report(session, account.id, prop_name, token)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "sync_google_analytics: report error for property %s: %s", prop_id, exc
            )


# Register with the Celery sync dispatcher (side-effect on import)
register_platform_sync(Platform.google_analytics.value, sync_google_analytics)
