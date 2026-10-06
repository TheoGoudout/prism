"""
Tests for the mailing platform syncs (Mailchimp, Klaviyo, Brevo), against the
test database. All HTTP calls are mocked — no real platform is contacted.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlmodel import Session, select

from app.integrations.platforms import SYNC_FUNCTIONS
from app.integrations.platforms.brevo import sync_brevo
from app.integrations.platforms.klaviyo import sync_klaviyo
from app.integrations.platforms.mailchimp import sync_mailchimp
from app.models.integration import Integration, Platform, PlatformAccount
from app.models.metrics import ContentType, MetricSnapshot, Post
from tests.utils.integration import create_fake_integration
from tests.utils.user import create_random_user
from tests.utils.workspace import create_random_workspace

NOW = datetime.now(UTC)
RECENT = (NOW - timedelta(days=2)).isoformat()
OLD = (NOW - timedelta(days=90)).isoformat()


def _response(body: Any, status_code: int = 200) -> MagicMock:
    resp = MagicMock(status_code=status_code)
    resp.json.return_value = body
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock(status_code=status_code)
        )
    return resp


def _router(routes: dict[str, Any]) -> Callable[..., MagicMock]:
    """A fake httpx.get / httpx.post answering by URL suffix."""

    def handler(url: str, **_: Any) -> MagicMock:
        for suffix, body in routes.items():
            if url.endswith(suffix):
                return body if isinstance(body, MagicMock) else _response(body)
        raise AssertionError(f"Unexpected request to {url}")

    return handler


def _integration(db: Session, platform: Platform) -> Integration:
    workspace = create_random_workspace(db, create_random_user(db))
    return create_fake_integration(
        db, workspace, platform=platform, external_account_name="Acme"
    )


def _accounts(db: Session, integration: Integration) -> list[PlatformAccount]:
    db.refresh(integration)
    return sorted(integration.accounts, key=lambda a: a.external_id)


def _posts(db: Session, account: PlatformAccount) -> list[Post]:
    return list(
        db.exec(select(Post).where(Post.platform_account_id == account.id)).all()
    )


def _snapshot(db: Session, account: PlatformAccount) -> MetricSnapshot | None:
    return db.exec(
        select(MetricSnapshot).where(
            MetricSnapshot.platform_account_id == account.id,
            MetricSnapshot.date == date.today(),
        )
    ).first()


@pytest.mark.parametrize(
    ("platform", "sync"),
    [
        (Platform.mailchimp, sync_mailchimp),
        (Platform.klaviyo, sync_klaviyo),
        (Platform.brevo, sync_brevo),
    ],
)
def test_registered_in_sync_registry(platform: Platform, sync: Any) -> None:
    assert SYNC_FUNCTIONS[platform] is sync


# ---------------------------------------------------------------------------
# Mailchimp
# ---------------------------------------------------------------------------

_MAILCHIMP_LISTS = {
    "lists": [
        {"id": "L1", "name": "Newsletter", "stats": {"member_count": 1200}},
        {"id": "L2", "name": "Customers", "stats": {"member_count": 300}},
    ]
}
_MAILCHIMP_CAMPAIGNS = {
    "campaigns": [
        {
            "id": "C1",
            "send_time": RECENT,
            "emails_sent": 1000,
            "recipients": {"list_id": "L1"},
            "settings": {"subject_line": "October news", "title": "Oct"},
            "long_archive_url": "https://mailchi.mp/acme/oct",
            "report_summary": {
                "opens": 700,
                "unique_opens": 400,
                "clicks": 150,
                "subscriber_clicks": 100,
            },
        },
        # Sent to a list the account no longer has: skipped
        {
            "id": "C2",
            "send_time": RECENT,
            "recipients": {"list_id": "gone"},
            "settings": {},
        },
    ]
}


def _mailchimp_get(campaigns: Any = _MAILCHIMP_CAMPAIGNS) -> Callable[..., MagicMock]:
    return _router(
        {
            "/oauth2/metadata": {"api_endpoint": "https://us6.api.mailchimp.com"},
            "us6.api.mailchimp.com/3.0/lists": _MAILCHIMP_LISTS,
            "us6.api.mailchimp.com/3.0/campaigns": campaigns,
        }
    )


def test_mailchimp_sync_stores_audiences_and_campaigns(db: Session) -> None:
    integration = _integration(db, Platform.mailchimp)
    with patch("httpx.get", side_effect=_mailchimp_get()) as get:
        sync_mailchimp(db, integration, "mc-tok")

    newsletter, customers = _accounts(db, integration)
    assert newsletter.name == "Newsletter"
    assert newsletter.account_type == "audience"
    assert _snapshot(db, newsletter).followers_count == 1200  # type: ignore[union-attr]
    assert _snapshot(db, customers).followers_count == 300  # type: ignore[union-attr]

    [post] = _posts(db, newsletter)
    assert post.external_id == "C1"
    assert post.content_type == ContentType.email
    assert post.text == "October news"
    assert post.permalink == "https://mailchi.mp/acme/oct"
    assert post.impressions == 1000
    assert post.views == 400
    assert post.engagements == 100
    assert post.clicks == 150
    assert post.engagement_rate == pytest.approx(100 / 400)
    assert _posts(db, customers) == []

    campaigns_call = next(
        c for c in get.call_args_list if c.args[0].endswith("/campaigns")
    )
    assert campaigns_call.kwargs["params"]["status"] == "sent"
    assert campaigns_call.kwargs["headers"]["Authorization"] == "Bearer mc-tok"


def test_mailchimp_campaign_errors_keep_the_audiences(db: Session) -> None:
    integration = _integration(db, Platform.mailchimp)
    with patch("httpx.get", side_effect=_mailchimp_get(_response({}, 500))):
        sync_mailchimp(db, integration, "mc-tok")

    assert len(_accounts(db, integration)) == 2


# ---------------------------------------------------------------------------
# Klaviyo
# ---------------------------------------------------------------------------

_KLAVIYO_CAMPAIGNS = {
    "data": [
        {
            "id": "K1",
            "attributes": {"name": "Fall sale", "status": "Sent", "send_time": RECENT},
            "relationships": {"campaign-messages": {"data": [{"id": "M1"}]}},
        },
        {
            "id": "K2",
            "attributes": {"name": "Draft", "status": "Draft", "send_time": None},
        },
        {
            "id": "K3",
            "attributes": {"name": "Old", "status": "Sent", "send_time": OLD},
        },
    ],
    "included": [
        {
            "type": "campaign-message",
            "id": "M1",
            "attributes": {"definition": {"content": {"subject": "30% off"}}},
        }
    ],
    # Not followed: an older campaign was reached
    "links": {"next": "https://a.klaviyo.com/api/campaigns/?page[cursor]=x"},
}
_KLAVIYO_METRICS = {
    "data": [
        {"id": "MET1", "attributes": {"name": "Opened Email"}},
        {"id": "MET2", "attributes": {"name": "Placed Order"}},
    ]
}
_KLAVIYO_REPORT = {
    "data": {
        "attributes": {
            "results": [
                {
                    "groupings": {"campaign_id": "K1", "campaign_message_id": "M1"},
                    "statistics": {
                        "delivered": 900,
                        "recipients": 950,
                        "opens_unique": 300,
                        "clicks_unique": 60,
                        "clicks": 80,
                    },
                },
                {
                    "groupings": {"campaign_id": "K1", "campaign_message_id": "M2"},
                    "statistics": {"delivered": 100, "opens_unique": 50},
                },
            ]
        }
    }
}


def test_klaviyo_sync_stores_the_account_and_campaigns(db: Session) -> None:
    integration = _integration(db, Platform.klaviyo)
    get = _router(
        {"/api/campaigns/": _KLAVIYO_CAMPAIGNS, "/api/metrics/": _KLAVIYO_METRICS}
    )
    with (
        patch("httpx.get", side_effect=get),
        patch("httpx.post", return_value=_response(_KLAVIYO_REPORT)) as post,
    ):
        sync_klaviyo(db, integration, "kl-tok")

    [account] = _accounts(db, integration)
    assert account.external_id == integration.external_account_id
    assert account.name == "Acme"

    [email] = _posts(db, account)
    assert email.external_id == "K1"
    assert email.text == "30% off"
    # Both messages of the campaign are summed
    assert email.impressions == 1000
    assert email.views == 350
    assert email.engagements == 60
    assert email.clicks == 80

    attributes = post.call_args.kwargs["json"]["data"]["attributes"]
    assert attributes["conversion_metric_id"] == "MET2"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer kl-tok"


def test_klaviyo_sync_without_recent_campaigns_skips_the_report(
    db: Session,
) -> None:
    integration = _integration(db, Platform.klaviyo)
    with (
        patch("httpx.get", side_effect=_router({"/api/campaigns/": {"data": []}})),
        patch("httpx.post") as post,
    ):
        sync_klaviyo(db, integration, "kl-tok")

    post.assert_not_called()
    assert len(_accounts(db, integration)) == 1


# ---------------------------------------------------------------------------
# Brevo
# ---------------------------------------------------------------------------

_BREVO_LISTS = {
    "count": 2,
    "lists": [
        {"id": 2, "name": "Newsletter", "uniqueSubscribers": 800},
        {"id": 7, "name": "VIP", "totalSubscribers": 40},
    ],
}
_BREVO_CAMPAIGNS = {
    "campaigns": [
        {
            "id": 31,
            "name": "October",
            "subject": "Our October picks",
            "sentDate": RECENT,
            "shareLink": "https://sendib.me/abc",
            "statistics": {
                "campaignStats": [
                    {
                        "listId": 2,
                        "delivered": 780,
                        "uniqueViews": 300,
                        "uniqueClicks": 45,
                        "clickers": 70,
                    },
                    {
                        "listId": 7,
                        "delivered": 40,
                        "uniqueViews": 30,
                        "uniqueClicks": 10,
                        "clickers": 12,
                    },
                    # A list that was deleted since: skipped
                    {"listId": 99, "delivered": 5},
                ]
            },
        }
    ]
}


def test_brevo_sync_stores_lists_and_campaigns_per_list(db: Session) -> None:
    integration = _integration(db, Platform.brevo)
    get = _router(
        {"/v3/contacts/lists": _BREVO_LISTS, "/v3/emailCampaigns": _BREVO_CAMPAIGNS}
    )
    with patch("httpx.get", side_effect=get) as mock_get:
        sync_brevo(db, integration, "xkeysib-key")

    newsletter, vip = _accounts(db, integration)
    assert (newsletter.external_id, vip.external_id) == ("2", "7")
    assert _snapshot(db, newsletter).followers_count == 800  # type: ignore[union-attr]
    assert _snapshot(db, vip).followers_count == 40  # type: ignore[union-attr]

    [post] = _posts(db, newsletter)
    assert post.external_id == "31"
    assert post.content_type == ContentType.email
    assert post.text == "Our October picks"
    assert post.permalink == "https://sendib.me/abc"
    assert (post.impressions, post.views, post.engagements, post.clicks) == (
        780,
        300,
        45,
        70,
    )
    [vip_post] = _posts(db, vip)
    assert vip_post.impressions == 40

    for call in mock_get.call_args_list:
        assert call.kwargs["headers"]["api-key"] == "xkeysib-key"
