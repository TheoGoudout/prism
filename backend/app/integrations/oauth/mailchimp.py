"""
Mailchimp OAuth2 provider.

Mailchimp access tokens never expire and there is no refresh token. Each
account lives in one data center: its API base URL comes from the metadata
endpoint (see mailchimp_api_endpoint).
"""

from typing import Any

import httpx

from app.integrations.oauth.base import (
    AccountInfo,
    OAuthProvider,
    TokenResponse,
)
from app.models.integration import Platform

METADATA_URL = "https://login.mailchimp.com/oauth2/metadata"


def mailchimp_metadata(access_token: str) -> dict[str, Any]:
    """The token's account: its id, name, login and API endpoint."""
    resp = httpx.get(
        METADATA_URL,
        headers={"Authorization": f"OAuth {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    return data


def mailchimp_api_endpoint(access_token: str) -> str:
    """The account's API base URL, e.g. https://us6.api.mailchimp.com."""
    return str(mailchimp_metadata(access_token)["api_endpoint"]).rstrip("/")


class MailchimpOAuthProvider(OAuthProvider):
    PLATFORM = Platform.mailchimp
    AUTH_URL = "https://login.mailchimp.com/oauth2/authorize"
    TOKEN_URL = "https://login.mailchimp.com/oauth2/token"

    CLIENT_ID_SETTING = "MAILCHIMP_CLIENT_ID"
    CLIENT_SECRET_SETTING = "MAILCHIMP_CLIENT_SECRET"

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        data = self._post_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
            }
        )
        # Mailchimp tokens don't expire (expires_in is 0)
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=None,
            expires_at=None,
            raw=data,
        )

    def refresh(self, refresh_token: str) -> TokenResponse:
        raise NotImplementedError("Mailchimp access tokens don't expire")

    def get_account_info(self, access_token: str) -> AccountInfo:
        data = mailchimp_metadata(access_token)
        login = data.get("login") or {}
        return AccountInfo(
            external_id=str(data["user_id"]),
            name=data.get("accountname") or login.get("login_name") or "Mailchimp",
            avatar_url=login.get("avatar"),
        )


mailchimp_provider = MailchimpOAuthProvider()
