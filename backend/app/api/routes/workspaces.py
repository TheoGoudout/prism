import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.models.common import Message
from app.models.user import User
from app.models.workspace import (
    Workspace,
    WorkspaceCreate,
    WorkspaceMember,
    WorkspaceMemberAdd,
    WorkspaceMemberPublic,
    WorkspaceMembersPublic,
    WorkspaceMemberUpdate,
    WorkspacePublic,
    WorkspaceRole,
    WorkspacesPublic,
    WorkspaceUpdate,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


# ---------------------------------------------------------------------------
# Shared dependencies
# ---------------------------------------------------------------------------


def _get_workspace_or_404(workspace_id: uuid.UUID, session: SessionDep) -> Workspace:
    workspace = crud.get_workspace(session=session, workspace_id=workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


def _require_membership(
    workspace_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> WorkspaceMember:
    """Return the membership row or 404 (hides existence from non-members)."""
    member = crud.get_member(
        session=session, workspace_id=workspace_id, user_id=current_user.id
    )
    if not member:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return member


def _require_role(
    member: WorkspaceMember,
    *roles: WorkspaceRole,
    detail: str = "Insufficient permissions",
) -> None:
    if member.role not in roles:
        raise HTTPException(status_code=403, detail=detail)


WorkspaceDep = Annotated[Workspace, Depends(_get_workspace_or_404)]
MembershipDep = Annotated[WorkspaceMember, Depends(_require_membership)]


def _make_workspace_public(
    workspace: Workspace, role: WorkspaceRole
) -> WorkspacePublic:
    return WorkspacePublic(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        created_at=workspace.created_at,
        role=role,
    )


def _make_member_public(member: WorkspaceMember) -> WorkspaceMemberPublic:
    user: User = member.user  # type: ignore[assignment]
    return WorkspaceMemberPublic(
        user_id=member.user_id,
        role=member.role,
        created_at=member.created_at,
        user_email=user.email,
        user_full_name=user.full_name,
    )


# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------


@router.post("/", response_model=WorkspacePublic)
def create_workspace(
    *, session: SessionDep, current_user: CurrentUser, workspace_in: WorkspaceCreate
) -> Any:
    """Create a new workspace. The creator becomes the owner."""
    workspace = crud.create_workspace(
        session=session, workspace_in=workspace_in, owner_id=current_user.id
    )
    return _make_workspace_public(workspace, WorkspaceRole.owner)


@router.get("/", response_model=WorkspacesPublic)
def list_workspaces(
    session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    """List all workspaces the current user belongs to."""
    workspaces, count = crud.get_workspaces_for_user(
        session=session, user_id=current_user.id, skip=skip, limit=limit
    )
    items = []
    for ws in workspaces:
        member = crud.get_member(
            session=session, workspace_id=ws.id, user_id=current_user.id
        )
        items.append(_make_workspace_public(ws, member.role))  # type: ignore[union-attr]
    return WorkspacesPublic(data=items, count=count)


@router.get("/{workspace_id}", response_model=WorkspacePublic)
def get_workspace(
    membership: MembershipDep,
    workspace: WorkspaceDep,
) -> Any:
    """Get a workspace by ID (must be a member)."""
    return _make_workspace_public(workspace, membership.role)


@router.patch("/{workspace_id}", response_model=WorkspacePublic)
def update_workspace(
    *,
    session: SessionDep,
    membership: MembershipDep,
    workspace: WorkspaceDep,
    workspace_in: WorkspaceUpdate,
) -> Any:
    """Update workspace name/slug. Requires owner or admin role."""
    _require_role(membership, WorkspaceRole.owner, WorkspaceRole.admin)
    workspace = crud.update_workspace(
        session=session, workspace=workspace, workspace_in=workspace_in
    )
    return _make_workspace_public(workspace, membership.role)


@router.delete("/{workspace_id}", response_model=Message)
def delete_workspace(
    *,
    session: SessionDep,
    membership: MembershipDep,
    workspace: WorkspaceDep,
) -> Any:
    """Delete a workspace. Only the owner can do this."""
    _require_role(membership, WorkspaceRole.owner)
    crud.delete_workspace(session=session, workspace=workspace)
    return Message(message="Workspace deleted successfully")


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/members", response_model=WorkspaceMembersPublic)
def list_members(
    _membership: MembershipDep,  # membership check only
    workspace: WorkspaceDep,
    session: SessionDep,
) -> Any:
    """List all members of a workspace."""
    members = crud.get_members(session=session, workspace_id=workspace.id)
    return WorkspaceMembersPublic(
        data=[_make_member_public(m) for m in members],
        count=len(members),
    )


@router.post("/{workspace_id}/members", response_model=WorkspaceMemberPublic)
def add_member(
    *,
    session: SessionDep,
    membership: MembershipDep,
    workspace: WorkspaceDep,
    member_in: WorkspaceMemberAdd,
) -> Any:
    """Add a user to a workspace. Requires owner or admin role."""
    _require_role(membership, WorkspaceRole.owner, WorkspaceRole.admin)

    # Owners can only be set by existing owners
    if member_in.role == WorkspaceRole.owner and membership.role != WorkspaceRole.owner:
        raise HTTPException(status_code=403, detail="Only owners can add other owners")

    # Check the target user exists
    if member_in.email is not None:
        target_user = crud.get_user_by_email_case_insensitive(
            session=session, email=member_in.email
        )
        if not target_user:
            raise HTTPException(
                status_code=404,
                detail="No user with this email. Ask them to sign up first.",
            )
    else:
        target_user = session.get(User, member_in.user_id)
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

    # Check not already a member
    existing = crud.get_member(
        session=session, workspace_id=workspace.id, user_id=target_user.id
    )
    if existing:
        raise HTTPException(
            status_code=409, detail="User is already a member of this workspace"
        )

    member = crud.add_member(
        session=session,
        workspace_id=workspace.id,
        member_in=WorkspaceMemberAdd(user_id=target_user.id, role=member_in.role),
    )
    return _make_member_public(member)


@router.patch("/{workspace_id}/members/{user_id}", response_model=WorkspaceMemberPublic)
def update_member(
    *,
    session: SessionDep,
    membership: MembershipDep,
    workspace: WorkspaceDep,
    user_id: uuid.UUID,
    member_in: WorkspaceMemberUpdate,
) -> Any:
    """Update a member's role. Only owners can change roles."""
    _require_role(membership, WorkspaceRole.owner)

    target = crud.get_member(
        session=session, workspace_id=workspace.id, user_id=user_id
    )
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")

    # Prevent removing the last owner
    if target.role == WorkspaceRole.owner and member_in.role != WorkspaceRole.owner:
        owners = [
            m
            for m in crud.get_members(session=session, workspace_id=workspace.id)
            if m.role == WorkspaceRole.owner
        ]
        if len(owners) <= 1:
            raise HTTPException(
                status_code=409, detail="Cannot demote the last owner of a workspace"
            )

    member = crud.update_member(session=session, member=target, member_in=member_in)
    return _make_member_public(member)


@router.delete("/{workspace_id}/members/{user_id}", response_model=Message)
def remove_member(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    membership: MembershipDep,
    workspace: WorkspaceDep,
    user_id: uuid.UUID,
) -> Any:
    """
    Remove a member from the workspace.
    Members can remove themselves; owners/admins can remove others.
    """
    target = crud.get_member(
        session=session, workspace_id=workspace.id, user_id=user_id
    )
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")

    is_self = user_id == current_user.id
    if not is_self:
        _require_role(membership, WorkspaceRole.owner, WorkspaceRole.admin)
        # Admins cannot remove owners
        if (
            target.role == WorkspaceRole.owner
            and membership.role != WorkspaceRole.owner
        ):
            raise HTTPException(
                status_code=403, detail="Only owners can remove other owners"
            )

    # Prevent removing the last owner
    if target.role == WorkspaceRole.owner:
        owners = [
            m
            for m in crud.get_members(session=session, workspace_id=workspace.id)
            if m.role == WorkspaceRole.owner
        ]
        if len(owners) <= 1:
            raise HTTPException(
                status_code=409, detail="Cannot remove the last owner of a workspace"
            )

    crud.remove_member(session=session, member=target)
    return Message(message="Member removed successfully")
