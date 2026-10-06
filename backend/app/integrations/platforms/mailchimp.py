"""
Mailchimp sync (Marketing API 3.0).

For every audience (mailing list) of the account:
  - the audience is stored as a PlatformAccount
  - today's subscriber count becomes a MetricSnapshot
  - campaigns sent to it in the sync window become Posts (see
    app.integrations.mailing for how email metrics are mapped)
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session

from app import crud
from app.integrations.common import SYNC_WINDOW_DAYS, log_http_errors, parse_datetime
from app.integrations.http import get_json
from app.integrations.mailing import email_campaign_post, record_subscribers
from app.integrations.oauth.mailchimp import mailchimp_api_endpoint
from app.models.integration import Integration

# The API returns at most 1000 items per page
_PAGE_SIZE = 1000

_LIST_FIELDS = "lists.id,lists.name,lists.stats"
_CAMPAIGN_FIELDS = (
    "campaigns.id,campaigns.send_time,campaigns.emails_sent,"
    "campaigns.recipients.list_id,campaigns.settings.subject_line,"
    "campaigns.settings.title,campaigns.long_archive_url,campaigns.report_summary"
)


def _fetch_lists(api: str, token: str) -> list[dict[str, Any]]:
    data = get_json(
        f"{api}/3.0/lists",
        token=token,
        params={"count": _PAGE_SIZE, "fields": _LIST_FIELDS},
    )
    lists: list[dict[str, Any]] = data.get("lists", [])
    return lists


def _fetch_sent_campaigns(api: str, token: str) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=SYNC_WINDOW_DAYS)
    data = get_json(
        f"{api}/3.0/campaigns",
        token=token,
        params={
            "status": "sent",
            "since_send_time": since.isoformat(),
            "count": _PAGE_SIZE,
            "fields": _CAMPAIGN_FIELDS,
        },
    )
    campaigns: list[dict[str, Any]] = data.get("campaigns", [])
    return campaigns


def _sync_campaigns(
    session: Session,
    account_ids: dict[str, Any],
    api: str,
    token: str,
) -> None:
    for campaign in _fetch_sent_campaigns(api, token):
        account_id = account_ids.get(campaign.get("recipients", {}).get("list_id"))
        published_at = parse_datetime(campaign.get("send_time"))
        if account_id is None or not campaign.get("id") or published_at is None:
            continue
        settings = campaign.get("settings", {})
        report = campaign.get("report_summary") or {}
        crud.upsert_post(
            session=session,
            platform_account_id=account_id,
            post_in=email_campaign_post(
                external_id=campaign["id"],
                published_at=published_at,
                subject=settings.get("subject_line") or settings.get("title"),
                permalink=campaign.get("long_archive_url"),
                delivered=campaign.get("emails_sent"),
                unique_opens=report.get("unique_opens"),
                unique_clicks=report.get("subscriber_clicks"),
                clicks=report.get("clicks"),
                raw_data={"emails_sent": campaign.get("emails_sent"), **report},
            ),
        )


def sync_mailchimp(
    session: Session, integration: Integration, access_token: str
) -> None:
    """Sync every audience of the Mailchimp account, and its campaigns."""
    api = mailchimp_api_endpoint(access_token)
    account_ids: dict[str, Any] = {}
    for mailing_list in _fetch_lists(api, access_token):
        account = crud.upsert_platform_account(
            session=session,
            integration=integration,
            external_id=mailing_list["id"],
            name=mailing_list.get("name") or mailing_list["id"],
            account_type="audience",
        )
        account_ids[mailing_list["id"]] = account.id
        stats = mailing_list.get("stats") or {}
        record_subscribers(session, account.id, stats.get("member_count"), stats)

    with log_http_errors("Mailchimp campaigns"):
        _sync_campaigns(session, account_ids, api, access_token)
