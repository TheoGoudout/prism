import logging
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app import crud
from app.api.deps import (
    CurrentMember,
    SessionDep,
    get_current_member,
    require_manager,
)
from app.api.routes.oauth import redirect_uri
from app.integrations.apikey.base import InvalidApiKeyError
from app.integrations.oauth import registry
from app.integrations.oauth.base import OAuthState, generate_pkce_pair
from app.integrations.revocation import revoke_access
from app.models.integration import (
    ApiKeyConnect,
    Integration,
    IntegrationCreate,
    IntegrationPublic,
    OAuthConnectResponse,
    Platform,
    PlatformAccount,
    PlatformAccountPublic,
    PlatformAccountUpdate,
)
from app.models.workspace import WorkspaceMember
from app.worker.celery_app import QUEUE_UNAVAILABLE
from app.worker.tasks import sync as sync_tasks

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/integrations", tags=["integrations"]
)


def _require_available(platform: Platform) -> None:
    if not registry.is_available(platform):
        raise HTTPException(
            status_code=400,
            detail=f"The {platform.value} integration is not set up on this server",
        )


def _get_integration(
    session: SessionDep, member: WorkspaceMember, integration_id: uuid.UUID
) -> Integration:
    integration = crud.get_for_workspace(
        session, Integration, integration_id, member.workspace_id
    )
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    return integration


@router.get("/", response_model=list[IntegrationPublic])
def list_integrations(session: SessionDep, member: CurrentMember) -> Any:
    return crud.get_integrations_for_workspace(
        session=session, workspace_id=member.workspace_id
    )


@router.get(
    "/platforms",
    dependencies=[Depends(get_current_member)],
    response_model=list[Platform],
)
def list_available_platforms() -> Any:
    """The platforms that can be connected: those whose app is set up."""
    return registry.available_platforms()


@router.get("/connect/{platform}", response_model=OAuthConnectResponse)
def connect(platform: Platform, member: CurrentMember) -> Any:
    """
    Start connecting a platform: returns the provider's authorization URL to
    send the user to. The provider then calls back GET /oauth/callback/{platform}.
    """
    require_manager(member, "connect integrations")
    _require_available(platform)
    if registry.uses_api_key(platform):
        raise HTTPException(
            status_code=400,
            detail=f"The {platform.value} integration is connected with an API key",
        )
    provider = registry.get_provider(platform)

    verifier, challenge = generate_pkce_pair() if provider.USES_PKCE else (None, None)
    state = OAuthState(
        workspace_id=member.workspace_id,
        user_id=member.user_id,
        platform=platform,
        pkce_verifier=verifier,
    ).encode()
    auth_url = provider.get_auth_url(
        redirect_uri=redirect_uri(platform), state=state, code_challenge=challenge
    )
    return OAuthConnectResponse(authorization_url=auth_url)


@router.post("/connect/{platform}/api-key", response_model=IntegrationPublic)
def connect_with_api_key(
    session: SessionDep,
    member: CurrentMember,
    platform: Platform,
    connect_in: ApiKeyConnect,
) -> Any:
    """
    Connect a platform that is authorized with an API key (e.g. Brevo): the
    key is checked with the platform, then stored encrypted. Connecting the
    same account again replaces its key.
    """
    require_manager(member, "connect integrations")
    if not registry.uses_api_key(platform):
        raise HTTPException(
            status_code=400,
            detail=f"The {platform.value} integration is connected with OAuth",
        )
    api_key = connect_in.api_key.strip()
    provider = registry.get_api_key_provider(platform)
    try:
        account = provider.get_account_info(api_key)
    except InvalidApiKeyError:
        raise HTTPException(
            status_code=400,
            detail=f"{platform.value.capitalize()} rejected this API key",
        ) from None
    except httpx.HTTPError:
        logger.exception("Could not check the %s API key", platform.value)
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach {platform.value.capitalize()}, try again",
        ) from None

    integration = crud.upsert_integration(
        session=session,
        integration_in=IntegrationCreate(
            platform=platform,
            workspace_id=member.workspace_id,
            access_token=api_key,
            external_account_id=account.external_id,
            external_account_name=account.name,
            external_account_avatar=account.avatar_url,
        ),
    )
    # Pull data right away rather than waiting for the nightly sync
    sync_tasks.enqueue_sync(integration.id)
    return integration


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(
    session: SessionDep, member: CurrentMember, integration_id: uuid.UUID
) -> None:
    """
    Disconnect an integration and delete its accounts and synced metrics.
    Prism's access is also revoked on the platform where possible.
    """
    require_manager(member, "remove integrations")
    integration = _get_integration(session, member, integration_id)
    revoke_access(session, integration)
    crud.delete(session, integration)


@router.post("/{integration_id}/sync", status_code=status.HTTP_202_ACCEPTED)
def trigger_sync(
    session: SessionDep, member: CurrentMember, integration_id: uuid.UUID
) -> None:
    """Enqueue a sync now; it runs in the background."""
    require_manager(member, "trigger syncs")
    integration = _get_integration(session, member, integration_id)
    _require_available(integration.platform)
    if not sync_tasks.enqueue_sync(integration.id):
        raise HTTPException(status_code=503, detail=QUEUE_UNAVAILABLE)


@router.patch(
    "/{integration_id}/accounts/{account_id}", response_model=PlatformAccountPublic
)
def update_account(
    session: SessionDep,
    member: CurrentMember,
    integration_id: uuid.UUID,
    account_id: uuid.UUID,
    account_in: PlatformAccountUpdate,
) -> Any:
    """
    Show or hide one of the integration's accounts (e.g. a Facebook Page) in
    the workspace's dashboards. Hidden accounts keep syncing.
    """
    require_manager(member, "choose the accounts shown")
    account = crud.get_for_workspace(
        session, PlatformAccount, account_id, member.workspace_id
    )
    if account is None or account.integration_id != integration_id:
        raise HTTPException(status_code=404, detail="Account not found")
    return crud.set_platform_account_active(
        session=session, account=account, is_active=account_in.is_active
    )
