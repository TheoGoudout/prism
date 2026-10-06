"""
Klaviyo sync (REST API, JSON:API format).

Klaviyo campaigns are sent to any mix of lists and segments, so the whole
Klaviyo account is stored as a single PlatformAccount:
  - email campaigns sent in the sync window become its Posts (see
    app.integrations.mailing for how email metrics are mapped)
  - their metrics come from one campaign values report

Klaviyo has no cheap total of subscribers, so no follower count is stored.
The values report needs a conversion metric: "Placed Order" if the account
tracks orders, else any metric (conversions aren't stored).
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session

from app import crud
from app.integrations.common import SYNC_WINDOW_DAYS, parse_datetime
from app.integrations.http import get_json, post_json
from app.integrations.mailing import email_campaign_post
from app.integrations.oauth.klaviyo import KLAVIYO_API, klaviyo_headers
from app.models.integration import Integration

logger = logging.getLogger(__name__)

_STATISTICS = ["delivered", "recipients", "opens_unique", "clicks_unique", "clicks"]
# Campaign pages to read at most (sorted newest first)
_MAX_PAGES = 10


def _get(url: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_json(url, token=token, params=params, headers=klaviyo_headers())


def _subject(campaign: dict[str, Any], included: dict[str, dict[str, Any]]) -> str:
    """The subject of the campaign's first message, else the campaign's name."""
    messages = (
        campaign.get("relationships", {}).get("campaign-messages", {}).get("data", [])
    )
    for ref in messages:
        attributes = included.get(ref.get("id"), {})
        content = (attributes.get("definition") or attributes).get("content") or {}
        if content.get("subject"):
            return str(content["subject"])
    return str(campaign.get("attributes", {}).get("name") or "")


def _fetch_sent_campaigns(token: str, since: datetime) -> list[dict[str, Any]]:
    """Email campaigns sent since the date, with their subject."""
    campaigns: list[dict[str, Any]] = []
    url: str | None = f"{KLAVIYO_API}/campaigns/"
    params: dict[str, Any] | None = {
        "filter": "equals(messages.channel,'email')",
        "sort": "-scheduled_at",
        "include": "campaign-messages",
    }
    for _ in range(_MAX_PAGES):
        if url is None:
            break
        data = _get(url, token, params)
        included = {
            item["id"]: item.get("attributes", {})
            for item in data.get("included", [])
            if item.get("type") == "campaign-message"
        }
        reached_older = False
        for campaign in data.get("data", []):
            attributes = campaign.get("attributes", {})
            sent_at = parse_datetime(attributes.get("send_time"))
            if sent_at is None or attributes.get("status") != "Sent":
                continue
            if sent_at < since:
                reached_older = True
                continue
            campaigns.append(
                {
                    "id": campaign["id"],
                    "sent_at": sent_at,
                    "subject": _subject(campaign, included),
                }
            )
        if reached_older:
            break
        # The next page's URL carries the query parameters
        url, params = data.get("links", {}).get("next"), None
    return campaigns


def _conversion_metric_id(token: str) -> str | None:
    data = _get(f"{KLAVIYO_API}/metrics/", token)
    metrics = data.get("data", [])
    for metric in metrics:
        if metric.get("attributes", {}).get("name") == "Placed Order":
            return str(metric["id"])
    return str(metrics[0]["id"]) if metrics else None


def _fetch_campaign_statistics(
    token: str, since: datetime, until: datetime
) -> dict[str, dict[str, Any]]:
    """Campaign id → its email statistics over the window."""
    metric_id = _conversion_metric_id(token)
    if metric_id is None:
        logger.warning("Klaviyo account has no metric: no campaign statistics")
        return {}
    data = post_json(
        f"{KLAVIYO_API}/campaign-values-reports/",
        token=token,
        headers={**klaviyo_headers(), "content-type": "application/vnd.api+json"},
        body={
            "data": {
                "type": "campaign-values-report",
                "attributes": {
                    "statistics": _STATISTICS,
                    "timeframe": {
                        "start": since.isoformat(),
                        "end": until.isoformat(),
                    },
                    "conversion_metric_id": metric_id,
                    "filter": "equals(send_channel,'email')",
                },
            }
        },
    )
    stats: dict[str, dict[str, Any]] = {}
    for result in data.get("data", {}).get("attributes", {}).get("results", []):
        campaign_id = result.get("groupings", {}).get("campaign_id")
        if not campaign_id:
            continue
        # A campaign with several messages (e.g. A/B tests) has one result each
        totals = stats.setdefault(campaign_id, {})
        for name, value in (result.get("statistics") or {}).items():
            if isinstance(value, int | float):
                totals[name] = totals.get(name, 0) + value
    return stats


def _sync_campaigns(
    session: Session, platform_account_id: uuid.UUID, token: str
) -> None:
    now = datetime.now(UTC)
    since = now - timedelta(days=SYNC_WINDOW_DAYS)
    campaigns = _fetch_sent_campaigns(token, since)
    if not campaigns:
        return
    statistics = _fetch_campaign_statistics(token, since, now)
    for campaign in campaigns:
        stats = statistics.get(campaign["id"], {})
        crud.upsert_post(
            session=session,
            platform_account_id=platform_account_id,
            post_in=email_campaign_post(
                external_id=campaign["id"],
                published_at=campaign["sent_at"],
                subject=campaign["subject"] or None,
                delivered=stats.get("delivered", stats.get("recipients")),
                unique_opens=stats.get("opens_unique"),
                unique_clicks=stats.get("clicks_unique"),
                clicks=stats.get("clicks"),
                raw_data=stats or None,
            ),
        )


def sync_klaviyo(session: Session, integration: Integration, access_token: str) -> None:
    """Sync the Klaviyo account's email campaigns."""
    account = crud.upsert_platform_account(
        session=session,
        integration=integration,
        external_id=integration.external_account_id,
        name=integration.external_account_name,
        account_type="account",
    )
    _sync_campaigns(session, account.id, access_token)
