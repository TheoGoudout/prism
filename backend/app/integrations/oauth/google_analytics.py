"""Google Analytics (GA4) OAuth2 provider."""

import httpx

from app.integrations.oauth.base import (
    AccountInfo,
    OAuthProvider,
    TokenResponse,
)
from app.models.integration import Platform


class GoogleAnalyticsOAuthProvider(OAuthProvider):
    PLATFORM = Platform.google_analytics
    SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    REVOKE_URL = "https://oauth2.googleapis.com/revoke"

    CLIENT_ID_SETTING = "GOOGLE_CLIENT_ID"
    CLIENT_SECRET_SETTING = "GOOGLE_CLIENT_SECRET"

    def _extra_auth_params(self) -> dict[str, str]:
        return {
            "access_type": "offline",  # request refresh token
            "prompt": "consent",  # force consent screen to always get refresh token
        }

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
        return self._token_response(data, default_expires_in=3600)

    def refresh(self, refresh_token: str) -> TokenResponse:
        data = self._post_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
            }
        )
        # Google doesn't rotate refresh tokens: the same one keeps working
        return self._token_response(
            data, default_expires_in=3600, refresh_token=refresh_token
        )

    def revoke(self, *, access_token: str, refresh_token: str | None) -> bool:
        resp = httpx.post(
            self.REVOKE_URL, data={"token": refresh_token or access_token}, timeout=10
        )
        resp.raise_for_status()
        return True

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
