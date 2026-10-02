"""
The OAuth provider of each platform.

A platform is available only once its app is set up, i.e. its client id and
secret are configured: the others can't be connected or synced.
"""

import logging

from app.integrations.oauth.base import OAuthProvider
from app.integrations.oauth.facebook import facebook_provider
from app.integrations.oauth.google_analytics import google_analytics_provider
from app.integrations.oauth.instagram import instagram_provider
from app.integrations.oauth.linkedin import linkedin_provider
from app.integrations.oauth.tiktok import tiktok_provider
from app.integrations.oauth.twitter import twitter_provider
from app.models.integration import Platform

logger = logging.getLogger(__name__)

PROVIDERS: dict[Platform, OAuthProvider] = {
    provider.PLATFORM: provider
    for provider in (
        facebook_provider,
        instagram_provider,
        twitter_provider,
        linkedin_provider,
        tiktok_provider,
        google_analytics_provider,
    )
}


def get_provider(platform: Platform) -> OAuthProvider:
    try:
        return PROVIDERS[platform]
    except KeyError:
        raise ValueError(f"No OAuth provider for platform '{platform}'") from None


def is_available(platform: Platform) -> bool:
    """Whether the platform's app is set up."""
    provider = PROVIDERS.get(platform)
    return provider is not None and provider.is_configured


def available_platforms() -> list[Platform]:
    """The platforms whose app is set up, in registry order."""
    return [platform for platform in PROVIDERS if is_available(platform)]


def log_availability() -> None:
    """Log which platform integrations are activated and which are not."""
    for platform, provider in PROVIDERS.items():
        if provider.is_configured:
            logger.info("Platform integration activated: %s", platform.value)
        else:
            logger.warning(
                "Platform integration not activated: %s (missing %s)",
                platform.value,
                ", ".join(provider.missing_settings),
            )
    available = available_platforms()
    logger.info(
        "%d of %d platform integrations activated: %s",
        len(available),
        len(PROVIDERS),
        ", ".join(p.value for p in available) or "none",
    )
