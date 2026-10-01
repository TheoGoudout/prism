"""
One sync module per platform. Each exposes a function with the signature
``sync(session, integration, access_token)`` that stores the accounts,
daily snapshots and posts it finds.
"""

from collections.abc import Callable

from sqlmodel import Session

from app.integrations.platforms.facebook import sync_facebook
from app.integrations.platforms.google_analytics import sync_google_analytics
from app.integrations.platforms.instagram import sync_instagram
from app.integrations.platforms.linkedin import sync_linkedin
from app.integrations.platforms.tiktok import sync_tiktok
from app.integrations.platforms.twitter import sync_twitter
from app.models.integration import Integration, Platform

SyncFunction = Callable[[Session, Integration, str], None]

SYNC_FUNCTIONS: dict[Platform, SyncFunction] = {
    Platform.facebook: sync_facebook,
    Platform.instagram: sync_instagram,
    Platform.twitter: sync_twitter,
    Platform.linkedin: sync_linkedin,
    Platform.tiktok: sync_tiktok,
    Platform.google_analytics: sync_google_analytics,
}
