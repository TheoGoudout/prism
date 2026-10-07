"""LinkedIn OAuth2 provider."""

import httpx

from app.integrations.oauth.base import (
    AccountInfo,
    OAuthProvider,
    TokenResponse,
)
from app.models.integration import Platform

# LinkedIn access tokens last 60 days
_TOKEN_SECONDS = 60 * 24 * 60 * 60


class LinkedInOAuthProvider(OAuthProvider):
    PLATFORM = Platform.linkedin
    SCOPES = ["r_organization_social", "rw_organization_admin", "r_basicprofile"]
    AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
    TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

    CLIENT_ID_SETTING = "LINKEDIN_CLIENT_ID"
    CLIENT_SECRET_SETTING = "LINKEDIN_CLIENT_SECRET"

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
        return self._token_response(data, default_expires_in=_TOKEN_SECONDS)

    def refresh(self, refresh_token: str) -> TokenResponse:
        data = self._post_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
            }
        )
        return self._token_response(
            data, default_expires_in=_TOKEN_SECONDS, refresh_token=refresh_token
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
        except KeyError, IndexError:
            avatar_url = None
        return AccountInfo(external_id=data["id"], name=name, avatar_url=avatar_url)


linkedin_provider = LinkedInOAuthProvider()
