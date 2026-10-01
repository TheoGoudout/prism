"""
Abstract OAuth2 base for all platform integrations.

Each platform implements a concrete subclass and overrides:
  - PLATFORM          – the Platform enum value
  - SCOPES            – list of required OAuth scopes
  - AUTH_URL          – the provider's authorization endpoint
  - TOKEN_URL         – the provider's token endpoint
  - USES_PKCE         – whether the provider requires PKCE (S256)
  - get_account_info  – fetch the connected account's name / id / avatar
  - refresh           – exchange refresh_token for a new access_token

The connect / callback HTTP handlers live in api/routes/oauth.py and
delegate to the appropriate provider via the registry below.
"""
import base64
import hashlib
import secrets
import urllib.parse
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.encryption import open_oauth_state, seal_oauth_state
from app.models.integration import Platform

# How long a user has to complete the provider's consent screen.
STATE_MAX_AGE_SECONDS = 15 * 60


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    raw: dict[str, Any]  # full provider response, for debugging


@dataclass
class AccountInfo:
    external_id: str
    name: str
    avatar_url: str | None


# ---------------------------------------------------------------------------
# State parameter
# ---------------------------------------------------------------------------


@dataclass
class OAuthState:
    """
    Data carried through the provider round-trip in the `state` parameter.

    The state is encrypted and authenticated with a key derived from
    SECRET_KEY, and expires after STATE_MAX_AGE_SECONDS. It therefore can't be
    forged (to attach an account to someone else's workspace), replayed
    indefinitely, or read (the PKCE verifier stays secret).
    """

    workspace_id: uuid.UUID
    user_id: uuid.UUID
    platform: Platform
    pkce_verifier: str | None = None

    def encode(self) -> str:
        return seal_oauth_state(
            {
                "w": str(self.workspace_id),
                "u": str(self.user_id),
                "p": self.platform.value,
                "v": self.pkce_verifier,
                # Random nonce so that two states are never identical
                "n": secrets.token_urlsafe(8),
            }
        )

    @classmethod
    def decode(cls, state: str) -> "OAuthState":
        payload = open_oauth_state(state, max_age_seconds=STATE_MAX_AGE_SECONDS)
        try:
            return cls(
                workspace_id=uuid.UUID(payload["w"]),
                user_id=uuid.UUID(payload["u"]),
                platform=Platform(payload["p"]),
                pkce_verifier=payload.get("v"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid OAuth state payload") from exc


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


# ---------------------------------------------------------------------------
# Provider base class
# ---------------------------------------------------------------------------


class OAuthProvider(ABC):
    """Base class for OAuth2 platform connectors."""

    PLATFORM: Platform
    SCOPES: list[str] = []
    SCOPE_SEPARATOR: str = " "
    AUTH_URL: str = ""
    TOKEN_URL: str = ""
    USES_PKCE: bool = False
    # Name of the client identifier query param on the authorization URL
    CLIENT_ID_PARAM: str = "client_id"

    # -----------------------------------------------------------------------
    # Authorization URL
    # -----------------------------------------------------------------------

    def get_auth_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        params: dict[str, str] = {
            self.CLIENT_ID_PARAM: self._client_id(),
            "redirect_uri": redirect_uri,
            "scope": self.SCOPE_SEPARATOR.join(self.SCOPES),
            "response_type": "code",
            "state": state,
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        params.update(self._extra_auth_params())
        if extra_params:
            params.update(extra_params)
        return self.AUTH_URL + "?" + urllib.parse.urlencode(params)

    def _extra_auth_params(self) -> dict[str, str]:
        """Provider-specific additions to the authorization URL."""
        return {}

    # -----------------------------------------------------------------------
    # Token exchange
    # -----------------------------------------------------------------------

    @abstractmethod
    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        """Exchange an authorization code for tokens."""

    @abstractmethod
    def refresh(self, refresh_token: str) -> TokenResponse:
        """Exchange a refresh token for a new access token."""

    def refresh_credential(
        self, *, access_token: str, refresh_token: str | None
    ) -> str | None:
        """
        The credential to pass to refresh(), or None if the token can't be
        refreshed. Most providers use the refresh token; Meta exchanges the
        current long-lived access token instead.
        """
        return refresh_token

    # -----------------------------------------------------------------------
    # Account info
    # -----------------------------------------------------------------------

    @abstractmethod
    def get_account_info(self, access_token: str) -> AccountInfo:
        """Return the connected account's id, name, and avatar."""

    # -----------------------------------------------------------------------
    # Subclass helpers
    # -----------------------------------------------------------------------

    @abstractmethod
    def _client_id(self) -> str: ...

    @abstractmethod
    def _client_secret(self) -> str: ...

    def _post_token(self, data: dict[str, Any]) -> dict[str, Any]:
        """POST to TOKEN_URL and return the JSON response."""
        resp = httpx.post(self.TOKEN_URL, data=data, timeout=10)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Registry — maps Platform enum → provider instance
# ---------------------------------------------------------------------------

_registry: dict[Platform, OAuthProvider] = {}


def register(provider: OAuthProvider) -> None:
    _registry[provider.PLATFORM] = provider


def get_provider(platform: Platform) -> OAuthProvider:
    provider = _registry.get(platform)
    if provider is None:
        raise ValueError(f"No OAuth provider registered for platform '{platform}'")
    return provider


def available_platforms() -> list[Platform]:
    return list(_registry.keys())
