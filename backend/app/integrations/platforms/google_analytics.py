"""
Google Analytics 4 sync.

For every GA4 property the user can access:
  - the property is stored as a PlatformAccount
  - a daily report over the sync window becomes MetricSnapshots

GA4 metrics are mapped onto the closest normalised fields:
screenPageViews → views, sessions → impressions, totalUsers → reach,
conversions → clicks. All raw values are kept in raw_data.
"""

import uuid
from datetime import date, timedelta
from typing import Any

from sqlmodel import Session

from app import crud
from app.integrations.common import SYNC_WINDOW_DAYS, log_http_errors
from app.integrations.http import get_json, post_json
from app.models.integration import Integration
from app.models.metrics import MetricSnapshotUpsert

GA_ADMIN_API = "https://analyticsadmin.googleapis.com/v1beta"
GA_DATA_API = "https://analyticsdata.googleapis.com/v1beta"

_REPORT_METRICS = [
    "sessions",
    "totalUsers",
    "screenPageViews",
    "bounceRate",
    "conversions",
    "engagementRate",
]


def _fetch_ga4_properties(token: str) -> list[dict[str, Any]]:
    data = get_json(f"{GA_ADMIN_API}/properties", token=token)
    properties = []
    for prop in data.get("properties", []):
        name: str = prop.get("name", "")  # "properties/123456789"
        prop_id = name.rsplit("/", 1)[-1]
        properties.append(
            {
                "property_id": prop_id,
                "property_name": name,
                "display_name": prop.get("displayName", prop_id),
            }
        )
    return properties


def _as_int(value: float | None) -> int | None:
    return None if value is None else int(value)


def _sync_property_report(
    session: Session, platform_account_id: uuid.UUID, property_name: str, token: str
) -> None:
    end = date.today()
    report = post_json(
        f"{GA_DATA_API}/{property_name}:runReport",
        token=token,
        body={
            "dateRanges": [
                {
                    "startDate": (end - timedelta(days=SYNC_WINDOW_DAYS)).isoformat(),
                    "endDate": end.isoformat(),
                }
            ],
            "dimensions": [{"name": "date"}],
            "metrics": [{"name": name} for name in _REPORT_METRICS],
        },
    )
    metric_names = [m["name"] for m in report.get("metricHeaders", [])]

    for row in report.get("rows", []):
        try:
            day_str = row["dimensionValues"][0]["value"]  # YYYYMMDD
            day = date(int(day_str[:4]), int(day_str[4:6]), int(day_str[6:8]))
        except (KeyError, IndexError, ValueError):
            continue
        values: dict[str, float | None] = dict.fromkeys(_REPORT_METRICS)
        for name, cell in zip(metric_names, row.get("metricValues", []), strict=False):
            try:
                values[name] = float(cell["value"])
            except (KeyError, ValueError):
                pass

        crud.upsert_metric_snapshot(
            session=session,
            platform_account_id=platform_account_id,
            snapshot_in=MetricSnapshotUpsert(
                date=day,
                views=_as_int(values["screenPageViews"]),
                impressions=_as_int(values["sessions"]),
                reach=_as_int(values["totalUsers"]),
                clicks=_as_int(values["conversions"]),
                raw_data=values,
            ),
        )


def sync_google_analytics(
    session: Session, integration: Integration, access_token: str
) -> None:
    """Sync every GA4 property the user can access."""
    for prop in _fetch_ga4_properties(access_token):
        account = crud.upsert_platform_account(
            session=session,
            integration=integration,
            external_id=prop["property_id"],
            name=prop["display_name"],
            account_type="property",
        )
        with log_http_errors(f"Google Analytics report for {prop['property_id']}"):
            _sync_property_report(
                session, account.id, prop["property_name"], access_token
            )
