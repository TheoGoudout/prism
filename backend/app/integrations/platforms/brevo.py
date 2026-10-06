"""
Brevo sync (API v3, authorized with the account's API key).

For every contact list of the account:
  - the list is stored as a PlatformAccount
  - today's subscriber count becomes a MetricSnapshot
  - email campaigns sent to it in the sync window become Posts, with the
    statistics of that list (Brevo reports them per list, so a campaign sent
    to two lists counts once in each)

See app.integrations.mailing for how email metrics are mapped.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session

from app import crud
from app.integrations.apikey.brevo import brevo_get
from app.integrations.common import SYNC_WINDOW_DAYS, log_http_errors, parse_datetime
from app.integrations.mailing import email_campaign_post, record_subscribers
from app.models.integration import Integration

# Largest page size the API accepts
_LISTS_PAGE_SIZE = 50
_CAMPAIGNS_PAGE_SIZE = 100
# Pages to read at most
_MAX_PAGES = 20


def _fetch_lists(api_key: str) -> list[dict[str, Any]]:
    lists: list[dict[str, Any]] = []
    for page in range(_MAX_PAGES):
        data = brevo_get(
            "contacts/lists",
            api_key,
            {"limit": _LISTS_PAGE_SIZE, "offset": page * _LISTS_PAGE_SIZE},
        )
        batch = data.get("lists") or []
        lists.extend(batch)
        if len(batch) < _LISTS_PAGE_SIZE or len(lists) >= data.get("count", 0):
            break
    return lists


def _fetch_sent_campaigns(api_key: str) -> list[dict[str, Any]]:
    end = datetime.now(UTC)
    start = end - timedelta(days=SYNC_WINDOW_DAYS)
    campaigns: list[dict[str, Any]] = []
    for page in range(_MAX_PAGES):
        data = brevo_get(
            "emailCampaigns",
            api_key,
            {
                "type": "classic",
                "status": "sent",
                "startDate": start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "endDate": end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "limit": _CAMPAIGNS_PAGE_SIZE,
                "offset": page * _CAMPAIGNS_PAGE_SIZE,
                "excludeHtmlContent": "true",
            },
        )
        batch = data.get("campaigns") or []
        campaigns.extend(batch)
        if len(batch) < _CAMPAIGNS_PAGE_SIZE:
            break
    return campaigns


def _sync_campaigns(
    session: Session, account_ids: dict[int, uuid.UUID], api_key: str
) -> None:
    for campaign in _fetch_sent_campaigns(api_key):
        published_at = parse_datetime(campaign.get("sentDate"))
        if campaign.get("id") is None or published_at is None:
            continue
        for stats in (campaign.get("statistics") or {}).get("campaignStats") or []:
            account_id = account_ids.get(stats.get("listId"))
            if account_id is None:
                continue
            crud.upsert_post(
                session=session,
                platform_account_id=account_id,
                post_in=email_campaign_post(
                    external_id=str(campaign["id"]),
                    published_at=published_at,
                    subject=campaign.get("subject") or campaign.get("name"),
                    permalink=campaign.get("shareLink"),
                    delivered=stats.get("delivered"),
                    unique_opens=stats.get("uniqueViews"),
                    unique_clicks=stats.get("uniqueClicks"),
                    # Brevo's "clickers" is the total number of clicks
                    clicks=stats.get("clickers"),
                    raw_data=stats,
                ),
            )


def sync_brevo(session: Session, integration: Integration, access_token: str) -> None:
    """Sync every contact list of the Brevo account, and its campaigns."""
    account_ids: dict[int, uuid.UUID] = {}
    for contact_list in _fetch_lists(access_token):
        if contact_list.get("id") is None:
            continue
        account = crud.upsert_platform_account(
            session=session,
            integration=integration,
            external_id=str(contact_list["id"]),
            name=contact_list.get("name") or str(contact_list["id"]),
            account_type="list",
        )
        account_ids[contact_list["id"]] = account.id
        subscribers = contact_list.get("uniqueSubscribers")
        if subscribers is None:
            subscribers = contact_list.get("totalSubscribers")
        record_subscribers(session, account.id, subscribers, contact_list)

    with log_http_errors("Brevo campaigns"):
        _sync_campaigns(session, account_ids, access_token)
