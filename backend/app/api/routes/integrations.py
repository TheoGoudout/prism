import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app import crud
from app.api.deps import CurrentMember, SessionDep, require_manager
from app.api.routes.oauth import redirect_uri
from app.integrations.oauth import registry
from app.integrations.oauth.base import OAuthState, generate_pkce_pair
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


@router.get("/connect/{platform}", response_model=OAuthConnectResponse)
def connect(platform: Platform, member: CurrentMember) -> Any:
    """
    Start connecting a platform: returns the provider's authorization URL to
    send the user to. The provider then calls back GET /oauth/callback/{platform}.
    """
    require_manager(member, "connect integrations")
    try:
        provider = registry.get_provider(platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
    """Disconnect an integration and delete its accounts and synced metrics."""
    require_manager(member, "remove integrations")
    crud.delete(session, _get_integration(session, member, integration_id))


@router.post("/{integration_id}/sync", status_code=status.HTTP_202_ACCEPTED)
def trigger_sync(
    session: SessionDep, member: CurrentMember, integration_id: uuid.UUID
) -> None:
    """Enqueue a sync now; it runs in the background."""
    require_manager(member, "trigger syncs")
    integration = _get_integration(session, member, integration_id)
    sync_tasks.sync_integration.delay(str(integration.id))
