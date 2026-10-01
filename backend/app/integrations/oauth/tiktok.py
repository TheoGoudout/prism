"""TikTok Business API OAuth2 provider."""

from datetime import timedelta

import httpx

from app.core.config import settings
from app.integrations.oauth.base import (
    AccountInfo,
    OAuthProvider,
    TokenResponse,
    register,
)
from app.models.integration import Platform


class TikTokOAuthProvider(OAuthProvider):
    PLATFORM = Platform.tiktok
    SCOPES = [
        "user.info.basic",
        "video.list",
        "video.insights",
        "tiktok.user.insights.creator",
    ]
    AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
    TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
    # TikTok names the client identifier `client_key` and comma-separates scopes
    CLIENT_ID_PARAM = "client_key"
    SCOPE_SEPARATOR = ","

    def _client_id(self) -> str:
        return settings.TIKTOK_CLIENT_KEY

    def _client_secret(self) -> str:
        return settings.TIKTOK_CLIENT_SECRET

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        resp = httpx.post(
            self.TOKEN_URL,
            data={
                "client_key": self._client_id(),
                "client_secret": self._client_secret(),
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", resp.json())
        expires_at = self._now_utc() + timedelta(seconds=data.get("expires_in", 86400))
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            raw=data,
        )

    def refresh(self, refresh_token: str) -> TokenResponse:
        resp = httpx.post(
            self.TOKEN_URL,
            data={
                "client_key": self._client_id(),
                "client_secret": self._client_secret(),
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", resp.json())
        expires_at = self._now_utc() + timedelta(seconds=data.get("expires_in", 86400))
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_at=expires_at,
            raw=data,
        )

    def get_account_info(self, access_token: str) -> AccountInfo:
        resp = httpx.get(
            "https://open.tiktokapis.com/v2/user/info/",
            params={"fields": "open_id,display_name,avatar_url"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {}).get("user", {})
        return AccountInfo(
            external_id=data["open_id"],
            name=data.get("display_name", "TikTok Account"),
            avatar_url=data.get("avatar_url"),
        )


tiktok_provider = TikTokOAuthProvider()
register(tiktok_provider)
