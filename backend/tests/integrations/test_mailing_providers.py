"""
Mailing platform providers: Mailchimp and Klaviyo (OAuth), Brevo (API key).
All HTTP calls are mocked — no real platform is contacted.
"""

import urllib.parse
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.integrations.apikey.base import InvalidApiKeyError
from app.integrations.apikey.brevo import brevo_provider
from app.integrations.oauth.klaviyo import klaviyo_provider
from app.integrations.oauth.mailchimp import (
    mailchimp_api_endpoint,
    mailchimp_provider,
)


def _response(body: Any, status_code: int = 200) -> MagicMock:
    resp = MagicMock(status_code=status_code)
    resp.json.return_value = body
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock(status_code=status_code)
        )
    return resp


def _query(url: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))


# ---------------------------------------------------------------------------
# Mailchimp
# ---------------------------------------------------------------------------

_MAILCHIMP_METADATA = {
    "dc": "us6",
    "user_id": 123456,
    "accountname": "Acme Newsletter",
    "api_endpoint": "https://us6.api.mailchimp.com",
    "login": {"login_name": "acme", "avatar": "https://example.com/a.png"},
}


def test_mailchimp_exchange_code_returns_non_expiring_token() -> None:
    with patch(
        "app.integrations.oauth.base.httpx.post",
        return_value=_response({"access_token": "mc-tok", "expires_in": 0}),
    ) as post:
        token = mailchimp_provider.exchange_code(
            code="c", redirect_uri="http://localhost/cb"
        )

    assert post.call_args.kwargs["data"]["grant_type"] == "authorization_code"
    assert token.access_token == "mc-tok"
    assert token.refresh_token is None
    assert token.expires_at is None


def test_mailchimp_get_account_info_uses_metadata() -> None:
    with patch(
        "app.integrations.oauth.mailchimp.httpx.get",
        return_value=_response(_MAILCHIMP_METADATA),
    ) as get:
        info = mailchimp_provider.get_account_info("mc-tok")

    assert get.call_args.kwargs["headers"] == {"Authorization": "OAuth mc-tok"}
    assert info.external_id == "123456"
    assert info.name == "Acme Newsletter"
    assert info.avatar_url == "https://example.com/a.png"


def test_mailchimp_api_endpoint() -> None:
    with patch(
        "app.integrations.oauth.mailchimp.httpx.get",
        return_value=_response(_MAILCHIMP_METADATA),
    ):
        assert mailchimp_api_endpoint("mc-tok") == "https://us6.api.mailchimp.com"


def test_mailchimp_has_no_revocation() -> None:
    assert not mailchimp_provider.revoke(access_token="t", refresh_token=None)


# ---------------------------------------------------------------------------
# Klaviyo
# ---------------------------------------------------------------------------


def test_klaviyo_auth_url_uses_pkce_and_read_scopes() -> None:
    url = klaviyo_provider.get_auth_url(
        redirect_uri="http://localhost/cb", state="s", code_challenge="chal"
    )
    params = _query(url)
    assert url.startswith("https://www.klaviyo.com/oauth/authorize?")
    assert params["code_challenge"] == "chal"
    assert "campaigns:read" in params["scope"].split(" ")


def test_klaviyo_exchange_code_requires_verifier() -> None:
    with pytest.raises(ValueError):
        klaviyo_provider.exchange_code(code="c", redirect_uri="http://localhost/cb")


def test_klaviyo_exchange_code_uses_basic_auth() -> None:
    body = {"access_token": "kl-tok", "refresh_token": "kl-ref", "expires_in": 3600}
    with patch(
        "app.integrations.oauth.klaviyo.httpx.post", return_value=_response(body)
    ) as post:
        token = klaviyo_provider.exchange_code(
            code="c", redirect_uri="http://localhost/cb", code_verifier="v"
        )

    assert post.call_args.kwargs["auth"] == (
        klaviyo_provider._client_id(),
        klaviyo_provider._client_secret(),
    )
    assert post.call_args.kwargs["data"]["code_verifier"] == "v"
    assert token.refresh_token == "kl-ref"
    assert token.expires_at is not None


def test_klaviyo_refresh_keeps_refresh_token_unless_rotated() -> None:
    with patch(
        "app.integrations.oauth.klaviyo.httpx.post",
        return_value=_response({"access_token": "new", "expires_in": 3600}),
    ):
        token = klaviyo_provider.refresh("kl-ref")
    assert token.access_token == "new"
    assert token.refresh_token == "kl-ref"


def test_klaviyo_revoke_revokes_the_refresh_token() -> None:
    with patch(
        "app.integrations.oauth.klaviyo.httpx.post", return_value=_response({})
    ) as post:
        assert klaviyo_provider.revoke(access_token="a", refresh_token="r")
    assert post.call_args.kwargs["data"] == {
        "token": "r",
        "token_type_hint": "refresh_token",
    }


def test_klaviyo_get_account_info() -> None:
    body = {
        "data": [
            {
                "id": "ACC123",
                "attributes": {
                    "contact_information": {"organization_name": "Acme Store"}
                },
            }
        ]
    }
    with patch(
        "app.integrations.oauth.klaviyo.httpx.get", return_value=_response(body)
    ) as get:
        info = klaviyo_provider.get_account_info("kl-tok")

    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer kl-tok"
    assert "revision" in get.call_args.kwargs["headers"]
    assert info.external_id == "ACC123"
    assert info.name == "Acme Store"


# ---------------------------------------------------------------------------
# Brevo (API key)
# ---------------------------------------------------------------------------


def test_brevo_get_account_info() -> None:
    body = {"organization_id": "org-1", "email": "a@acme.com", "companyName": "Acme"}
    with patch("httpx.get", return_value=_response(body)) as get:
        info = brevo_provider.get_account_info("xkeysib-123")

    assert get.call_args.args[0] == "https://api.brevo.com/v3/account"
    assert get.call_args.kwargs["headers"]["api-key"] == "xkeysib-123"
    assert info.external_id == "org-1"
    assert info.name == "Acme"


@pytest.mark.parametrize("status_code", [401, 403])
def test_brevo_rejected_key(status_code: int) -> None:
    with patch("httpx.get", return_value=_response({}, status_code)):
        with pytest.raises(InvalidApiKeyError):
            brevo_provider.get_account_info("bad")


def test_brevo_other_errors_propagate() -> None:
    with patch("httpx.get", return_value=_response({}, 503)):
        with pytest.raises(httpx.HTTPStatusError):
            brevo_provider.get_account_info("key")
