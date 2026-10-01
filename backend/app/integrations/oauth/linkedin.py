"""LinkedIn OAuth2 provider."""

from datetime import timedelta

import httpx

from app.core.config import settings
from app.integrations.oauth.base import (
    AccountInfo,
    OAuthProvider,
    TokenResponse,
)
from app.models.integration import Platform


class LinkedInOAuthProvider(OAuthProvider):
    PLATFORM = Platform.linkedin
    SCOPES = ["r_organization_social", "rw_organization_admin", "r_basicprofile"]
    AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
    TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

    def _client_id(self) -> str:
        return settings.LINKEDIN_CLIENT_ID

    def _client_secret(self) -> str:
        return settings.LINKEDIN_CLIENT_SECRET

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
        expires_at = self._now_utc() + timedelta(
            seconds=data.get("expires_in", 5184000)
        )
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            raw=data,
        )

    def refresh(self, refresh_token: str) -> TokenResponse:
        data = self._post_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
            }
        )
        expires_at = self._now_utc() + timedelta(
            seconds=data.get("expires_in", 5184000)
        )
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_at=expires_at,
            raw=data,
        )

    def get_account_info(self, access_token: str) -> AccountInfo:
        resp = httpx.get(
            "https://api.linkedin.com/v2/me",
            params={
                "projection": "(id,localizedFirstName,localizedLastName,profilePicture(displayImage~:playableStreams))"
            },
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        name = f"{data.get('localizedFirstName', '')} {data.get('localizedLastName', '')}".strip()
        # Extract smallest profile picture
        try:
            elements = data["profilePicture"]["displayImage~"]["elements"]
            avatar_url = elements[0]["identifiers"][0]["identifier"]
        except (KeyError, IndexError):
            avatar_url = None
        return AccountInfo(external_id=data["id"], name=name, avatar_url=avatar_url)


linkedin_provider = LinkedInOAuthProvider()
