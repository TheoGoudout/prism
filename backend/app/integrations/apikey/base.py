"""
Platforms connected with an API key instead of OAuth.

Some platforms (e.g. Brevo) offer no OAuth flow to third-party apps: the user
creates an API key in their account and pastes it into Prism. The key is
stored encrypted as the integration's access token. It never expires, has no
refresh token, and can't be revoked by Prism (the user deletes it on the
platform). No server setup is needed, so these platforms are always available.

Each platform implements a subclass with:
  - PLATFORM          – the Platform enum value
  - get_account_info  – check the key and return the account it belongs to
"""

from abc import ABC, abstractmethod

from app.integrations.oauth.base import AccountInfo
from app.models.integration import Platform


class InvalidApiKeyError(Exception):
    """The platform rejected the API key."""


class ApiKeyProvider(ABC):
    PLATFORM: Platform

    @abstractmethod
    def get_account_info(self, api_key: str) -> AccountInfo:
        """
        The account the key belongs to. Raises InvalidApiKeyError if the
        platform rejects the key, httpx errors on other failures.
        """
