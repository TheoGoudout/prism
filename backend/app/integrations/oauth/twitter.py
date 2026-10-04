"""Twitter/X OAuth2 (v2 API with PKCE)."""

from datetime import timedelta

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

    def _token_request(self, data: dict[str, str]) -> TokenResponse:
        resp = httpx.post(
            self.TOKEN_URL,
            data=data,
            auth=(self._client_id(), self._client_secret()),
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()
        expires_at = self._now_utc() + timedelta(seconds=body.get("expires_in", 7200))
        return TokenResponse(
            access_token=body["access_token"],
            # Twitter rotates refresh tokens on every use
            refresh_token=body.get("refresh_token", data.get("refresh_token")),
            expires_at=expires_at,
            raw=body,
        )

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        if not code_verifier:
            raise ValueError("Twitter requires a PKCE code_verifier")
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
