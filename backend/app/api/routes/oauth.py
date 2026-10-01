"""
OAuth2 connect / callback routes.

Flow:
  1. Frontend calls GET /oauth/connect/{platform}?workspace_id=<id>
     → receives a redirect URL for the provider. The URL carries an
       encrypted, expiring `state` that binds the request to the user,
       workspace and platform (and holds the PKCE verifier, if any).
  2. User authorises the app on the provider's site.
  3. Provider redirects to GET /oauth/callback/{platform}?code=...&state=...
     → server validates the state, re-checks the user's role, exchanges the
       code for tokens, creates or refreshes the Integration row, and
       redirects the user back to the frontend.
"""

import logging
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app import crud
from app.api.deps import CurrentMember, CurrentUser, SessionDep, require_manager
from app.core.config import settings
from app.integrations.oauth import registry
from app.integrations.oauth.base import OAuthState, generate_pkce_pair
from app.models.integration import Integration, IntegrationCreate, Platform
from app.worker.tasks import sync as sync_tasks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])


def _redirect_uri(platform: Platform) -> str:
    return (
        f"{settings.API_BASE_URL}{settings.API_V1_STR}/oauth/callback/{platform.value}"
    )


def _back_to_frontend(**params: str) -> RedirectResponse:
    """Send the user back to the Integrations page with a result to display."""
    return RedirectResponse(
        url=f"{settings.FRONTEND_HOST}/integrations?{urlencode(params)}",
        status_code=302,
    )


@router.get("/connect/{platform}")
def connect(
    platform: Platform, member: CurrentMember, current_user: CurrentUser
) -> Any:
    """Return the provider's authorization URL to redirect the user to."""
    require_manager(member, "connect integrations")
    try:
        provider = registry.get_provider(platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    verifier, challenge = generate_pkce_pair() if provider.USES_PKCE else (None, None)
    state = OAuthState(
        workspace_id=member.workspace_id,
        user_id=current_user.id,
        platform=platform,
        pkce_verifier=verifier,
    ).encode()
    auth_url = provider.get_auth_url(
        redirect_uri=_redirect_uri(platform), state=state, code_challenge=challenge
    )
    return {"authorization_url": auth_url}


@router.get("/callback/{platform}", include_in_schema=False)
def callback(
    platform: Platform,
    session: SessionDep,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """
    Called by the provider after the user authorises (or denies) access.
    Not authenticated: the user arrives via redirect, so their identity and
    workspace are recovered from the encrypted `state`.
    """
    try:
        oauth_state = OAuthState.decode(state or "")
        if oauth_state.platform != platform:
            raise ValueError("State was issued for a different platform")
    except ValueError:
        return _back_to_frontend(error="invalid_state")

    if error:  # e.g. the user clicked "Deny" on the consent screen
        return _back_to_frontend(error=error)
    if not code:
        return _back_to_frontend(error="missing_code")

    # Permissions may have changed while the user was on the provider's site
    member = crud.get_member(
        session=session,
        workspace_id=oauth_state.workspace_id,
        user_id=oauth_state.user_id,
    )
    if member is None or not member.role.can_manage:
        return _back_to_frontend(error="forbidden")

    try:
        integration = _connect_integration(session, oauth_state, code)
    except Exception:
        logger.exception("OAuth callback failed for platform %s", platform.value)
        return _back_to_frontend(error="connection_failed")

    # Pull data right away rather than waiting for the nightly sync
    try:
        sync_tasks.sync_integration.delay(str(integration.id))
    except Exception:
        logger.warning("Could not enqueue initial sync for %s", integration.id)

    return _back_to_frontend(connected="1")


def _connect_integration(
    session: Session, oauth_state: OAuthState, code: str
) -> Integration:
    """Exchange the authorization code and store the connected account."""
    provider = registry.get_provider(oauth_state.platform)
    token = provider.exchange_code(
        code=code,
        redirect_uri=_redirect_uri(oauth_state.platform),
        code_verifier=oauth_state.pkce_verifier,
    )
    account = provider.get_account_info(token.access_token)
    return crud.upsert_integration(
        session=session,
        integration_in=IntegrationCreate(
            platform=oauth_state.platform,
            workspace_id=oauth_state.workspace_id,
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            token_expires_at=token.expires_at,
            external_account_id=account.external_id,
            external_account_name=account.name,
            external_account_avatar=account.avatar_url,
        ),
    )
