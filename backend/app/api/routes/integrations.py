import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app import crud
from app.api.deps import (
    CurrentMember,
    SessionDep,
    get_current_member,
    require_manager,
)
from app.api.routes.oauth import redirect_uri
from app.integrations.oauth import registry
from app.integrations.oauth.base import OAuthState, generate_pkce_pair
from app.integrations.revocation import revoke_access
from app.models.integration import (
    Integration,
    IntegrationPublic,
    OAuthConnectResponse,
    Platform,
)
from app.models.workspace import WorkspaceMember
from app.worker.tasks import sync as sync_tasks

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
    integration = crud.get_integration(session=session, integration_id=integration_id)
    if integration is None or integration.workspace_id != member.workspace_id:
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
    sync_tasks.sync_integration.delay(str(integration.id))
