"""
Access-token lifecycle: refresh tokens before they expire.

Called by the sync task before each platform sync. Most providers issue
short-lived access tokens (Google ~1h, Twitter ~2h, TikTok ~24h) so without
this every nightly sync after the first would fail.
"""

import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlmodel import Session

from app import crud
from app.integrations.oauth import registry
from app.models.integration import Integration, Platform

logger = logging.getLogger(__name__)

# Refresh a little before expiry so a token can't lapse mid-sync.
REFRESH_MARGIN = timedelta(minutes=10)
# Meta long-lived tokens (~60 days) can only be extended while still valid,
# so renew them well ahead of time.
META_REFRESH_MARGIN = timedelta(days=7)


class TokenExpiredError(Exception):
    """The integration's credentials are no longer usable; user must reconnect."""


def _margin(integration: Integration) -> timedelta:
    if integration.platform in (Platform.facebook, Platform.instagram):
        return META_REFRESH_MARGIN
    return REFRESH_MARGIN


def ensure_fresh_token(*, session: Session, integration: Integration) -> None:
    """
    Refresh the integration's access token if it expires within the margin.

    Raises TokenExpiredError if the token is expired (or about to) and can't
    be refreshed. Transient network errors propagate so the caller can retry.
    """
    expires_at = integration.token_expires_at
    if expires_at is None:
        return  # provider issued a non-expiring token
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    now = datetime.now(UTC)
    if expires_at - now > _margin(integration):
        return

    provider = registry.get_provider(integration.platform)
    access_token = crud.get_access_token(integration) or ""
    credential = provider.refresh_credential(
        access_token=access_token, refresh_token=crud.get_refresh_token(integration)
    )
    already_expired = expires_at <= now

    if not credential:
        if already_expired:
            raise TokenExpiredError(
                "Access token expired and cannot be refreshed. Please reconnect."
            )
        return  # still valid for now; nothing we can do ahead of time

    try:
        token = provider.refresh(credential)
    except httpx.HTTPStatusError as exc:
        # 4xx: the provider rejected the credential (revoked, expired, ...)
        if 400 <= exc.response.status_code < 500:
            if already_expired:
                raise TokenExpiredError(
                    "Could not refresh access token "
                    f"({exc.response.status_code}). Please reconnect."
                ) from exc
            logger.warning(
                "Token refresh rejected for integration %s; current token "
                "still valid until %s",
                integration.id,
                expires_at.isoformat(),
            )
            return
        raise

    crud.update_integration_tokens(
        session=session,
        integration=integration,
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        expires_at=token.expires_at,
    )
    logger.info("Refreshed access token for integration %s", integration.id)
