import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.models.common import Message
from app.models.integration import (
    IntegrationPublic,
    IntegrationsPublic,
    Platform,
    PlatformAccountsPublic,
)
from app.models.workspace import WorkspaceRole

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _get_integration_or_404(
    integration_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Any:
    integration = crud.get_integration(session=session, integration_id=integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    # Workspace membership check — non-members get 404 to avoid info leakage
    member = crud.get_member(
        session=session,
        workspace_id=integration.workspace_id,
        user_id=current_user.id,
    )
    if not member:
        raise HTTPException(status_code=404, detail="Integration not found")
    return integration, member


# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------


@router.get("/", response_model=IntegrationsPublic)
def list_integrations(
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    platform: Platform | None = None,
) -> Any:
    """List all integrations for a workspace the user belongs to."""
    member = crud.get_member(
        session=session, workspace_id=workspace_id, user_id=current_user.id
    )
    if not member:
        raise HTTPException(status_code=404, detail="Workspace not found")

    integrations = crud.get_integrations_for_workspace(
        session=session, workspace_id=workspace_id, platform=platform
    )
    return IntegrationsPublic(
        data=[IntegrationPublic.model_validate(i) for i in integrations],
        count=len(integrations),
    )


@router.get("/{integration_id}", response_model=IntegrationPublic)
def get_integration(
    integration_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """Get a single integration (must be workspace member)."""
    integration, _ = _get_integration_or_404(integration_id, session, current_user)
    return IntegrationPublic.model_validate(integration)


@router.delete("/{integration_id}", response_model=Message)
def delete_integration(
    integration_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Disconnect (delete) an integration and all its platform accounts.
    Requires owner or admin role in the workspace.
    """
    integration, member = _get_integration_or_404(integration_id, session, current_user)
    if member.role not in (WorkspaceRole.owner, WorkspaceRole.admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners and admins can remove integrations",
        )
    crud.delete_integration(session=session, integration=integration)
    return Message(message="Integration disconnected successfully")


# ---------------------------------------------------------------------------
# Platform accounts
# ---------------------------------------------------------------------------


@router.get("/{integration_id}/accounts", response_model=PlatformAccountsPublic)
def list_accounts(
    integration_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """List all platform accounts belonging to an integration."""
    integration, _ = _get_integration_or_404(integration_id, session, current_user)
    accounts = crud.get_accounts_for_integration(
        session=session, integration_id=integration.id
    )
    return PlatformAccountsPublic(data=list(accounts), count=len(accounts))


# ---------------------------------------------------------------------------
# Manual sync (stub — will be wired to Celery in Step 5)
# ---------------------------------------------------------------------------


@router.post(
    "/{integration_id}/sync",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Message,
)
def trigger_sync(
    integration_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Enqueue a manual sync for this integration.
    Returns 202 immediately; the sync runs in the background.
    """
    integration, member = _get_integration_or_404(integration_id, session, current_user)
    if member.role not in (WorkspaceRole.owner, WorkspaceRole.admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners and admins can trigger syncs",
        )
    from app.worker.tasks.sync import sync_integration

    sync_integration.delay(str(integration.id))
    return Message(message="Sync enqueued")
