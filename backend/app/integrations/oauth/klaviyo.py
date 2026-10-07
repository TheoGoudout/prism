"""Klaviyo OAuth2 provider (PKCE, client credentials sent with Basic auth)."""

import httpx

from app.integrations.oauth.base import (
    AccountInfo,
    OAuthProvider,
    TokenResponse,
)
from app.models.integration import Platform

KLAVIYO_API = "https://a.klaviyo.com/api"
# The API version every request is pinned to
KLAVIYO_REVISION = "2025-10-15"


def klaviyo_headers() -> dict[str, str]:
    return {"revision": KLAVIYO_REVISION, "accept": "application/vnd.api+json"}


class KlaviyoOAuthProvider(OAuthProvider):
    PLATFORM = Platform.klaviyo
    SCOPES = ["accounts:read", "campaigns:read", "lists:read", "metrics:read"]
    AUTH_URL = "https://www.klaviyo.com/oauth/authorize"
    TOKEN_URL = "https://a.klaviyo.com/oauth/token"
    REVOKE_URL = "https://a.klaviyo.com/oauth/revoke"
    USES_PKCE = True

    CLIENT_ID_SETTING = "KLAVIYO_CLIENT_ID"
    CLIENT_SECRET_SETTING = "KLAVIYO_CLIENT_SECRET"

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        if not code_verifier:
            raise ValueError("Klaviyo requires a PKCE code_verifier")
        data = self._post_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            basic_auth=True,
        )
        return self._token_response(data, default_expires_in=3600)

    def refresh(self, refresh_token: str) -> TokenResponse:
        data = self._post_token(
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            basic_auth=True,
        )
        # Klaviyo may rotate the refresh token
        return self._token_response(
            data, default_expires_in=3600, refresh_token=refresh_token
        )

    def revoke(self, *, access_token: str, refresh_token: str | None) -> bool:
        token, hint = (
            (refresh_token, "refresh_token")
            if refresh_token
            else (access_token, "access_token")
        )
        resp = httpx.post(
            self.REVOKE_URL,
            data={"token": token, "token_type_hint": hint},
            auth=(self._client_id(), self._client_secret()),
            timeout=10,
        )
        resp.raise_for_status()
        return True

    def get_account_info(self, access_token: str) -> AccountInfo:
        resp = httpx.get(
            f"{KLAVIYO_API}/accounts/",
            headers={"Authorization": f"Bearer {access_token}", **klaviyo_headers()},
            timeout=10,
        )
        resp.raise_for_status()
        account = resp.json()["data"][0]
        contact = account.get("attributes", {}).get("contact_information") or {}
        return AccountInfo(
            external_id=account["id"],
            name=contact.get("organization_name")
            or contact.get("default_sender_name")
            or "Klaviyo",
            avatar_url=None,
        )


klaviyo_provider = KlaviyoOAuthProvider()
