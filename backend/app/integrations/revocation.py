"""
Revoke Prism's access on the platform when an integration is disconnected,
so the app also disappears from the user's connected apps there.

Providers revoke the whole grant (user + app), not a single token. The same
person may have connected the same account in several workspaces (or, on
Meta, both Facebook and Instagram), so revoking is skipped while another
integration still relies on that grant.
"""

import logging

from sqlmodel import Session, col, select

from app import crud
from app.integrations.oauth import registry
from app.models.integration import Integration, Platform

logger = logging.getLogger(__name__)

# Platforms whose integrations share one OAuth app, hence one grant per user
_META = (Platform.facebook, Platform.instagram)


def _grant_platforms(platform: Platform) -> tuple[Platform, ...]:
    return _META if platform in _META else (platform,)


def _grant_owner(integration: Integration) -> str:
    provider = registry.get_provider(integration.platform)
    return provider.grant_owner_id(
        access_token=crud.get_access_token(integration) or "",
        external_account_id=integration.external_account_id,
    )


def _grant_is_shared(session: Session, integration: Integration, owner: str) -> bool:
    others = session.exec(
        select(Integration).where(
            col(Integration.platform).in_(_grant_platforms(integration.platform)),
            Integration.id != integration.id,
        )
    ).all()
    for other in others:
        try:
            if _grant_owner(other) == owner:
                return True
        except Exception:
            # Unknown owner (e.g. its token expired): assume it may be shared
            return True
    return False


def revoke_access(session: Session, integration: Integration) -> bool:
    """
    Revoke the integration's grant on the platform, if possible and not
    shared. Best effort: failures are logged, never raised, so they can't
    block a disconnect. Returns whether access was revoked.
    """
    access_token = crud.get_access_token(integration)
    if not access_token:
        return False
    if not registry.is_available(integration.platform):
        logger.info(
            "Not revoking %s integration %s: the integration is not set up",
            integration.platform.value,
            integration.id,
        )
        return False
    provider = registry.get_provider(integration.platform)
    try:
        if _grant_is_shared(session, integration, _grant_owner(integration)):
            logger.info(
                "Not revoking %s integration %s: its grant is still in use",
                integration.platform.value,
                integration.id,
            )
            return False
        return provider.revoke(
            access_token=access_token,
            refresh_token=crud.get_refresh_token(integration),
        )
    except Exception:
        logger.warning(
            "Could not revoke %s integration %s on the platform",
            integration.platform.value,
            integration.id,
            exc_info=True,
        )
        return False
