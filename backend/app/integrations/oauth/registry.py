"""
Import every OAuth provider so each registers itself, and re-export the
registry lookups. Import from here (not from base) when you need a provider.
"""
import app.integrations.oauth.facebook  # noqa: F401
import app.integrations.oauth.google_analytics  # noqa: F401
import app.integrations.oauth.instagram  # noqa: F401
import app.integrations.oauth.linkedin  # noqa: F401
import app.integrations.oauth.tiktok  # noqa: F401
import app.integrations.oauth.twitter  # noqa: F401
from app.integrations.oauth.base import available_platforms, get_provider

__all__ = ["available_platforms", "get_provider"]
