"""The OAuth provider of each platform."""

from app.integrations.oauth.base import OAuthProvider
from app.integrations.oauth.facebook import facebook_provider
from app.integrations.oauth.google_analytics import google_analytics_provider
from app.integrations.oauth.instagram import instagram_provider
from app.integrations.oauth.linkedin import linkedin_provider
from app.integrations.oauth.tiktok import tiktok_provider
from app.integrations.oauth.twitter import twitter_provider
from app.models.integration import Platform

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
