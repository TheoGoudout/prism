"""TikTok Business API OAuth2 provider."""

import httpx

from app.integrations.oauth.base import (
    AccountInfo,
    OAuthProvider,
    TokenResponse,
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
    REVOKE_URL = "https://open.tiktokapis.com/v2/oauth/revoke/"
    # TikTok names the client identifier `client_key` and comma-separates scopes
    CLIENT_ID_PARAM = "client_key"
    SCOPE_SEPARATOR = ","

    CLIENT_ID_SETTING = "TIKTOK_CLIENT_KEY"
    CLIENT_SECRET_SETTING = "TIKTOK_CLIENT_SECRET"

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        return self._tiktok_token(
            {
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            }
        )

    def refresh(self, refresh_token: str) -> TokenResponse:
        return self._tiktok_token(
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            refresh_token=refresh_token,
        )

    def _tiktok_token(
        self, data: dict[str, str], refresh_token: str | None = None
    ) -> TokenResponse:
        body = self._post_token(
            {
                "client_key": self._client_id(),
                "client_secret": self._client_secret(),
                **data,
            }
        )
        return self._token_response(
            body.get("data", body),
            default_expires_in=86400,
            refresh_token=refresh_token,
        )

    def revoke(self, *, access_token: str, refresh_token: str | None) -> bool:
        resp = httpx.post(
            self.REVOKE_URL,
            data={
                "client_key": self._client_id(),
                "client_secret": self._client_secret(),
                "token": access_token,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True

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
