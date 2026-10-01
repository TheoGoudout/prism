import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app import crud
from app.api.deps import (
    CurrentMember,
    CurrentUser,
    SessionDep,
    get_workspace_member,
    require_manager,
)
from app.models.common import Message
from app.models.integration import (
    Integration,
    IntegrationPublic,
    IntegrationsPublic,
    Platform,
    PlatformAccountsPublic,
)
from app.models.workspace import WorkspaceMember
from app.worker.tasks import sync as sync_tasks

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _get_integration(
    integration_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> tuple[Integration, WorkspaceMember]:
    """The integration and the caller's membership of its workspace."""
    integration = crud.get_integration(session=session, integration_id=integration_id)
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    try:
        member = get_workspace_member(session, current_user, integration.workspace_id)
    except HTTPException:
        # Same 404 for non-members, so they can't tell the integration exists
        raise HTTPException(status_code=404, detail="Integration not found")
    return integration, member


IntegrationAccess = Annotated[
    tuple[Integration, WorkspaceMember], Depends(_get_integration)
]


@router.get("/", response_model=IntegrationsPublic)
def list_integrations(
    session: SessionDep, member: CurrentMember, platform: Platform | None = None
) -> Any:
    """List the integrations of a workspace the user belongs to."""
    integrations = crud.get_integrations_for_workspace(
        session=session, workspace_id=member.workspace_id, platform=platform
    )
    return IntegrationsPublic(data=integrations, count=len(integrations))


@router.get("/{integration_id}", response_model=IntegrationPublic)
def get_integration(access: IntegrationAccess) -> Any:
    integration, _ = access
    return integration


@router.delete("/{integration_id}", response_model=Message)
def delete_integration(session: SessionDep, access: IntegrationAccess) -> Any:
    """Disconnect an integration and delete its accounts and synced metrics."""
    integration, member = access
    require_manager(member, "remove integrations")
    crud.delete(session, integration)
    return Message(message="Integration disconnected successfully")


@router.get("/{integration_id}/accounts", response_model=PlatformAccountsPublic)
def list_accounts(session: SessionDep, access: IntegrationAccess) -> Any:
    """The pages / profiles / properties found by the last sync."""
    integration, _ = access
    accounts = crud.get_accounts_for_integration(
        session=session, integration_id=integration.id
    )
    return PlatformAccountsPublic(data=accounts, count=len(accounts))


@router.post(
    "/{integration_id}/sync",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Message,
)
def trigger_sync(access: IntegrationAccess) -> Any:
    """Enqueue a sync now; it runs in the background."""
    integration, member = access
    require_manager(member, "trigger syncs")
    sync_tasks.sync_integration.delay(str(integration.id))
    return Message(message="Sync enqueued")
