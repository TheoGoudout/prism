"""Twitter/X OAuth2 (v2 API with PKCE)."""

import httpx

from app.integrations.oauth.base import (
    AccountInfo,
    OAuthProvider,
    TokenResponse,
)
from app.models.integration import Platform


class TwitterOAuthProvider(OAuthProvider):
    PLATFORM = Platform.twitter
    SCOPES = ["tweet.read", "users.read", "offline.access"]
    AUTH_URL = "https://twitter.com/i/oauth2/authorize"
    TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
    REVOKE_URL = "https://api.x.com/2/oauth2/revoke"
    USES_PKCE = True

    CLIENT_ID_SETTING = "TWITTER_CLIENT_ID"
    CLIENT_SECRET_SETTING = "TWITTER_CLIENT_SECRET"

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        if not code_verifier:
            raise ValueError("Twitter requires a PKCE code_verifier")
        data = self._post_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            basic_auth=True,
        )
        return self._token_response(data, default_expires_in=7200)

    def refresh(self, refresh_token: str) -> TokenResponse:
        data = self._post_token(
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            basic_auth=True,
        )
        # Twitter rotates refresh tokens on every use
        return self._token_response(
            data, default_expires_in=7200, refresh_token=refresh_token
        )

    def revoke(self, *, access_token: str, refresh_token: str | None) -> bool:
        tokens = [(access_token, "access_token")]
        if refresh_token:
            tokens.append((refresh_token, "refresh_token"))
        for token, hint in tokens:
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
            "https://api.twitter.com/2/users/me",
            params={"user.fields": "profile_image_url"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return AccountInfo(
            external_id=data["id"],
            name=data["name"],
            avatar_url=data.get("profile_image_url"),
        )


twitter_provider = TwitterOAuthProvider()
