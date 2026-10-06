"""
The provider of each platform: an OAuth provider, or an API key provider for
the platforms connected with an API key.

An OAuth platform is available only once its app is set up, i.e. its client
id and secret are configured: the others can't be connected or synced. API
key platforms need no setup, so they are always available.
"""

import logging

from app.integrations.apikey.base import ApiKeyProvider
from app.integrations.apikey.brevo import brevo_provider
from app.integrations.oauth.base import OAuthProvider
from app.integrations.oauth.facebook import facebook_provider
from app.integrations.oauth.google_analytics import google_analytics_provider
from app.integrations.oauth.instagram import instagram_provider
from app.integrations.oauth.klaviyo import klaviyo_provider
from app.integrations.oauth.linkedin import linkedin_provider
from app.integrations.oauth.mailchimp import mailchimp_provider
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
        mailchimp_provider,
        klaviyo_provider,
    )
}

API_KEY_PROVIDERS: dict[Platform, ApiKeyProvider] = {
    provider.PLATFORM: provider for provider in (brevo_provider,)
}


def get_provider(platform: Platform) -> OAuthProvider:
    try:
        return PROVIDERS[platform]
    except KeyError:
        raise ValueError(f"No OAuth provider for platform '{platform}'") from None


def get_api_key_provider(platform: Platform) -> ApiKeyProvider:
    try:
        return API_KEY_PROVIDERS[platform]
    except KeyError:
        raise ValueError(f"No API key provider for platform '{platform}'") from None


def uses_api_key(platform: Platform) -> bool:
    """Whether the platform is connected with an API key rather than OAuth."""
    return platform in API_KEY_PROVIDERS


def is_available(platform: Platform) -> bool:
    """Whether the platform can be used: an API key one, or its app is set up."""
    if uses_api_key(platform):
        return True
    provider = PROVIDERS.get(platform)
    return provider is not None and provider.is_configured


def available_platforms() -> list[Platform]:
    """The platforms that can be used, in registry order."""
    return [
        platform
        for platform in (*PROVIDERS, *API_KEY_PROVIDERS)
        if is_available(platform)
    ]


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
    for platform in API_KEY_PROVIDERS:
        logger.info("Platform integration activated: %s (API key)", platform.value)
    available = available_platforms()
    logger.info(
        "%d of %d platform integrations activated: %s",
        len(available),
        len(PROVIDERS) + len(API_KEY_PROVIDERS),
        ", ".join(p.value for p in available) or "none",
    )
