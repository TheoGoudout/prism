"""
Instagram OAuth2 provider, using Instagram Login (the "Instagram API with
Instagram Login" of the Meta app).

People sign in with Instagram itself: unlike Facebook Login, no Facebook Page
is needed. Only professional (Business or Creator) accounts can sign in.

Instagram integrations connected before through Facebook Login keep their
Facebook token, which is refreshed and revoked through Facebook.
"""

from typing import Any

from app.integrations.http import get_json
from app.integrations.meta import (
    INSTAGRAM_GRAPH_API,
    graph_get,
    uses_instagram_login,
)
from app.integrations.oauth.base import AccountInfo, OAuthProvider, TokenResponse
from app.integrations.oauth.facebook import facebook_provider
from app.models.integration import Platform

# Instagram long-lived tokens last 60 days.
_LONG_LIVED_SECONDS = 60 * 24 * 60 * 60


class InstagramOAuthProvider(OAuthProvider):
    PLATFORM = Platform.instagram
    SCOPES = ["instagram_business_basic", "instagram_business_manage_insights"]
    SCOPE_SEPARATOR = ","
    AUTH_URL = "https://www.instagram.com/oauth/authorize"
    TOKEN_URL = "https://api.instagram.com/oauth/access_token"
    # Token endpoints are not versioned
    TOKEN_API = "https://graph.instagram.com"

    CLIENT_ID_SETTING = "INSTAGRAM_APP_ID"
    CLIENT_SECRET_SETTING = "INSTAGRAM_APP_SECRET"

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        data = self._post_token(
            {
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            }
        )
        # Older API versions return the token itself, newer ones a list of one
        if "data" in data:
            data = data["data"][0]
        # The code exchange yields a short-lived (1h) token. Swap it right
        # away for a long-lived (60 day) one so nightly syncs work.
        return self._long_lived(
            get_json(
                f"{self.TOKEN_API}/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": self._client_secret(),
                    "access_token": data["access_token"],
                },
            )
        )

    def refresh(self, refresh_token: str) -> TokenResponse:
        """
        Instagram has no refresh tokens: a valid long-lived token (at least
        24h old) is exchanged for a fresh one.
        """
        if not uses_instagram_login(refresh_token):
            return facebook_provider.refresh(refresh_token)
        return self._long_lived(
            get_json(
                f"{self.TOKEN_API}/refresh_access_token",
                params={
                    "grant_type": "ig_refresh_token",
                    "access_token": refresh_token,
                },
            )
        )

    def refresh_credential(
        self, *, access_token: str, refresh_token: str | None
    ) -> str | None:
        return access_token

    def revoke(self, *, access_token: str, refresh_token: str | None) -> bool:
        # Instagram Login has no revocation endpoint: people remove the app
        # from Instagram's settings (Website permissions → Apps and websites)
        if not uses_instagram_login(access_token):
            return facebook_provider.revoke(
                access_token=access_token, refresh_token=refresh_token
            )
        return False

    def grant_owner_id(self, *, access_token: str, external_account_id: str) -> str:
        if not uses_instagram_login(access_token):
            # The account id is the Instagram account's; the grant is the
            # Facebook user's, shared with that user's Facebook integrations
            return str(graph_get("me", access_token, {"fields": "id"})["id"])
        return external_account_id

    def get_account_info(self, access_token: str) -> AccountInfo:
        data = graph_get(
            "me",
            access_token,
            {"fields": "user_id,username,name,profile_picture_url"},
            api=INSTAGRAM_GRAPH_API,
        )
        return AccountInfo(
            # `user_id` is the account's Instagram id, the one Facebook Login
            # returns too; `id` is only valid for this app
            external_id=str(data.get("user_id") or data["id"]),
            name=data.get("name") or data.get("username") or "Instagram Account",
            avatar_url=data.get("profile_picture_url"),
        )

    def _long_lived(self, data: dict[str, Any]) -> TokenResponse:
        return self._token_response(data, default_expires_in=_LONG_LIVED_SECONDS)


instagram_provider = InstagramOAuthProvider()
