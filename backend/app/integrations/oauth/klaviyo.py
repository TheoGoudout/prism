"""Klaviyo OAuth2 provider (PKCE, client credentials sent with Basic auth)."""

from datetime import timedelta
from typing import Any

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

    def _token_request(self, data: dict[str, str]) -> TokenResponse:
        resp = httpx.post(
            self.TOKEN_URL,
            data=data,
            auth=(self._client_id(), self._client_secret()),
            timeout=10,
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        return TokenResponse(
            access_token=body["access_token"],
            # Klaviyo may rotate the refresh token
            refresh_token=body.get("refresh_token", data.get("refresh_token")),
            expires_at=self._now_utc()
            + timedelta(seconds=body.get("expires_in", 3600)),
            raw=body,
        )

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        if not code_verifier:
            raise ValueError("Klaviyo requires a PKCE code_verifier")
        return self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            }
        )

    def refresh(self, refresh_token: str) -> TokenResponse:
        return self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
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
