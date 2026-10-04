"""Meta Graph API access shared by Facebook and Instagram (login and sync)."""

import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import httpx

from app.integrations.common import SYNC_WINDOW_DAYS, parse_datetime
from app.integrations.http import get_json

logger = logging.getLogger(__name__)

# Pinned Graph API version. Meta supports each version for ~2 years; see
# https://developers.facebook.com/docs/graph-api/changelog/versions/
GRAPH_API_VERSION = "v25.0"
GRAPH_API = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
FACEBOOK_DIALOG_URL = f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth"


def graph_get(
    path: str, token: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """GET a Graph API object or edge. Meta takes the token as a query param."""
    return get_json(
        f"{GRAPH_API}/{path}", params={**(params or {}), "access_token": token}
    )


def graph_get_all(
    path: str, token: str, params: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """GET every item of a paginated Graph API edge, following `paging.next`."""
    data = graph_get(path, token, params)
    items: list[dict[str, Any]] = data.get("data", [])
    while next_url := (data.get("paging") or {}).get("next"):
        # The `next` URL already carries the token and the original params
        data = get_json(next_url)
        items.extend(data.get("data", []))
    return items


def first_value(entry: dict[str, Any]) -> Any:
    """The value of a lifetime insight entry ({"values": [{"value": …}]})."""
    values = entry.get("values") or [{}]
    return values[0].get("value")


def daily_insights(
    object_id: str, token: str, metrics: Sequence[str]
) -> dict[date, dict[str, Any]]:
    """
    Daily insights of a Page or Instagram account over the sync window, as
    {day: {metric name: value}}.

    Meta rejects the whole request if any one metric is invalid (e.g. newly
    deprecated, or not available for this account), so on a 400 each metric
    is fetched on its own and the unavailable ones are skipped.
    """
    end = date.today()
    start = end - timedelta(days=SYNC_WINDOW_DAYS)
    params: dict[str, Any] = {
        "period": "day",
        "since": int(datetime.combine(start, time(), UTC).timestamp()),
        "until": int(datetime.combine(end, time(), UTC).timestamp()),
    }

    def fetch(metric_names: str) -> list[dict[str, Any]]:
        data = graph_get(
            f"{object_id}/insights", token, {**params, "metric": metric_names}
        )
        entries: list[dict[str, Any]] = data.get("data", [])
        return entries

    try:
        entries = fetch(",".join(metrics))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 400:
            raise
        entries = []
        for metric in metrics:
            try:
                entries.extend(fetch(metric))
            except httpx.HTTPStatusError as metric_exc:
                logger.warning(
                    "%s: metric %s unavailable: %s", object_id, metric, metric_exc
                )

    by_day: dict[date, dict[str, Any]] = {}
    for entry in entries:
        for point in entry.get("values", []):
            end_time = parse_datetime(point.get("end_time"))
            if end_time is not None:
                by_day.setdefault(end_time.date(), {})[entry["name"]] = point.get(
                    "value"
                )
    return by_day
