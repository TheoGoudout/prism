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
import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.integrations.oauth import registry as oauth_registry
from app.integrations.oauth.base import OAuthState, generate_pkce_pair
from app.models.integration import IntegrationCreate, Platform
from app.models.workspace import WorkspaceRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])

_CONNECT_ROLES = (WorkspaceRole.owner, WorkspaceRole.admin)


def _redirect_uri(platform: Platform) -> str:
    return f"{settings.API_BASE_URL}{settings.API_V1_STR}/oauth/callback/{platform.value}"


def _frontend_redirect(**params: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"{settings.FRONTEND_HOST}/integrations?{urlencode(params)}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# Connect — return the provider's authorization URL
# ---------------------------------------------------------------------------


@router.get("/connect/{platform}")
def connect(
    platform: Platform,
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> Any:
    """Return the OAuth authorization URL for the given platform."""
    member = crud.get_member(
        session=session, workspace_id=workspace_id, user_id=current_user.id
    )
    if not member:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if member.role not in _CONNECT_ROLES:
        raise HTTPException(
            status_code=403, detail="Only owners and admins can connect integrations"
        )

    try:
        provider = oauth_registry.get_provider(platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    verifier, challenge = generate_pkce_pair() if provider.USES_PKCE else (None, None)
    state = OAuthState(
        workspace_id=workspace_id,
        user_id=current_user.id,
        platform=platform,
        pkce_verifier=verifier,
    ).encode()

    auth_url = provider.get_auth_url(
        redirect_uri=_redirect_uri(platform),
        state=state,
        code_challenge=challenge,
    )
    return {"authorization_url": auth_url}


# ---------------------------------------------------------------------------
# Callback — exchange code, create Integration, redirect to frontend
# ---------------------------------------------------------------------------


@router.get("/callback/{platform}", include_in_schema=False)
def callback(
    platform: Platform,
    session: SessionDep,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """
    OAuth2 callback — called by the provider after the user authorises
    (or denies) access. Not authenticated: the user arrives via redirect, so
    identity and workspace are recovered from the encrypted `state`.
    """
    try:
        if not state:
            raise ValueError("Missing state")
        oauth_state = OAuthState.decode(state)
        if oauth_state.platform != platform:
            raise ValueError("State was issued for a different platform")
    except ValueError:
        return RedirectResponse(
            url=f"{settings.FRONTEND_HOST}/integrations?error=invalid_state",
            status_code=302,
        )

    if error:
        # e.g. the user clicked "Deny" on the provider's consent screen
        return _frontend_redirect(error=error)
    if not code:
        return _frontend_redirect(error="missing_code")

    # Permissions may have changed while the user was on the provider's site
    member = crud.get_member(
        session=session,
        workspace_id=oauth_state.workspace_id,
        user_id=oauth_state.user_id,
    )
    if not member or member.role not in _CONNECT_ROLES:
        return _frontend_redirect(error="forbidden")

    try:
        provider = oauth_registry.get_provider(platform)
        token_resp = provider.exchange_code(
            code=code,
            redirect_uri=_redirect_uri(platform),
            code_verifier=oauth_state.pkce_verifier,
        )
        account_info = provider.get_account_info(token_resp.access_token)

        integration_in = IntegrationCreate(
            platform=platform,
            workspace_id=oauth_state.workspace_id,
            access_token=token_resp.access_token,
            refresh_token=token_resp.refresh_token,
            token_expires_at=token_resp.expires_at,
            external_account_id=account_info.external_id,
            external_account_name=account_info.name,
            external_account_avatar=account_info.avatar_url,
        )
        integration = crud.upsert_integration(
            session=session, integration_in=integration_in
        )
    except Exception:
        logger.exception("OAuth callback failed for platform %s", platform.value)
        return _frontend_redirect(error="connection_failed")

    # Pull data right away rather than waiting for the nightly sync
    try:
        from app.worker.tasks.sync import sync_integration

        sync_integration.delay(str(integration.id))
    except Exception:
        logger.warning("Could not enqueue initial sync for %s", integration.id)

    return _frontend_redirect(connected="1")
