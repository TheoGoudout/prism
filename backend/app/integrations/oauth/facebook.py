"""Facebook / Meta OAuth2 provider (also the base for Instagram Business)."""

from datetime import timedelta
from typing import Any

import httpx

from app.core.config import settings
from app.integrations.meta import FACEBOOK_DIALOG_URL, GRAPH_API
from app.integrations.oauth.base import (
    AccountInfo,
    OAuthProvider,
    TokenResponse,
    register,
)
from app.models.integration import Platform

# Meta long-lived user tokens last ~60 days.
_LONG_LIVED_SECONDS = 60 * 24 * 60 * 60


class FacebookOAuthProvider(OAuthProvider):
    PLATFORM = Platform.facebook
    SCOPES = ["pages_show_list", "pages_read_engagement", "read_insights"]
    SCOPE_SEPARATOR = ","
    AUTH_URL = FACEBOOK_DIALOG_URL
    TOKEN_URL = f"{GRAPH_API}/oauth/access_token"

    def _client_id(self) -> str:
        return settings.FACEBOOK_APP_ID

    def _client_secret(self) -> str:
        return settings.FACEBOOK_APP_SECRET

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        data = self._post_token(
            {
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
                "redirect_uri": redirect_uri,
                "code": code,
            }
        )
        # The code exchange yields a short-lived (~1-2h) user token. Swap it
        # right away for a long-lived (~60 day) one so nightly syncs work.
        return self.refresh(data["access_token"])

    def refresh(self, refresh_token: str) -> TokenResponse:
        """
        Meta has no refresh tokens: a valid (not yet expired) user token is
        exchanged for a fresh long-lived one via fb_exchange_token.
        """
        data = self._post_token(
            {
                "grant_type": "fb_exchange_token",
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
                "fb_exchange_token": refresh_token,
            }
        )
        expires_in = data.get("expires_in", _LONG_LIVED_SECONDS)
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=None,
            expires_at=self._now_utc() + timedelta(seconds=expires_in),
            raw=data,
        )

    def refresh_credential(
        self, *, access_token: str, refresh_token: str | None
    ) -> str | None:
        return access_token

    def get_account_info(self, access_token: str) -> AccountInfo:
        data = self._graph_get("me", access_token, {"fields": "id,name,picture"})
        return AccountInfo(
            external_id=data["id"],
            name=data["name"],
            avatar_url=(data.get("picture") or {}).get("data", {}).get("url"),
        )

    @staticmethod
    def _graph_get(
        path: str, access_token: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        resp = httpx.get(
            f"{GRAPH_API}/{path}",
            params={**(params or {}), "access_token": access_token},
            timeout=10,
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result


facebook_provider = FacebookOAuthProvider()
register(facebook_provider)
