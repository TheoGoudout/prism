"""Google Analytics (GA4) OAuth2 provider."""
from datetime import timedelta

import httpx

from app.core.config import settings
from app.integrations.oauth.base import AccountInfo, OAuthProvider, TokenResponse, register
from app.models.integration import Platform


class GoogleAnalyticsOAuthProvider(OAuthProvider):
    PLATFORM = Platform.google_analytics
    SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def _client_id(self) -> str:
        return settings.GOOGLE_CLIENT_ID

    def _client_secret(self) -> str:
        return settings.GOOGLE_CLIENT_SECRET

    def _extra_auth_params(self) -> dict[str, str]:
        return {
            "access_type": "offline",  # request refresh token
            "prompt": "consent",  # force consent screen to always get refresh token
        }

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        data = self._post_token({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._client_id(),
            "client_secret": self._client_secret(),
        })
        expires_at = self._now_utc() + timedelta(seconds=data.get("expires_in", 3600))
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            raw=data,
        )

    def refresh(self, refresh_token: str) -> TokenResponse:
        data = self._post_token({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._client_id(),
            "client_secret": self._client_secret(),
        })
        expires_at = self._now_utc() + timedelta(seconds=data.get("expires_in", 3600))
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=refresh_token,  # Google doesn't rotate refresh tokens
            expires_at=expires_at,
            raw=data,
        )

    def get_account_info(self, access_token: str) -> AccountInfo:
        resp = httpx.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return AccountInfo(
            external_id=data["id"],
            name=data.get("name") or data.get("email", "Google Account"),
            avatar_url=data.get("picture"),
        )


google_analytics_provider = GoogleAnalyticsOAuthProvider()
register(google_analytics_provider)
