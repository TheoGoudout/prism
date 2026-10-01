import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app import crud
from app.api.deps import CurrentMember, CurrentUser, SessionDep, require_manager
from app.models.common import Message
from app.models.user import User
from app.models.workspace import (
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
# Helpers
# ---------------------------------------------------------------------------


def _workspace_public(member: WorkspaceMember) -> WorkspacePublic:
    """The member's workspace, along with their role in it."""
    assert member.workspace is not None  # guaranteed by the foreign key
    return WorkspacePublic.model_validate(
        member.workspace, update={"role": member.role}
    )


def _member_public(member: WorkspaceMember) -> WorkspaceMemberPublic:
    assert member.user is not None  # guaranteed by the foreign key
    return WorkspaceMemberPublic(
        user_id=member.user_id,
        role=member.role,
        created_at=member.created_at,
        user_email=member.user.email,
        user_full_name=member.user.full_name,
    )


def _require_owner(member: WorkspaceMember, action: str) -> None:
    if member.role != WorkspaceRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only workspace owners can {action}",
        )


def _get_target_member(
    session: SessionDep, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> WorkspaceMember:
    target = crud.get_member(
        session=session, workspace_id=workspace_id, user_id=user_id
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return target


def _keep_an_owner(session: SessionDep, target: WorkspaceMember, action: str) -> None:
    """409 if ``target`` is the workspace's only owner: one must always remain."""
    if (
        target.role == WorkspaceRole.owner
        and crud.count_owners(session=session, workspace_id=target.workspace_id) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot {action} the last owner of a workspace",
        )


def _find_user(session: SessionDep, member_in: WorkspaceMemberAdd) -> User:
    if member_in.email is not None:
        user = crud.get_user_by_email_case_insensitive(
            session=session, email=member_in.email
        )
        if user is None:
            raise HTTPException(
                status_code=404,
                detail="No user with this email. Ask them to sign up first.",
            )
        return user
    user = session.get(User, member_in.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


@router.post("/", response_model=WorkspacePublic)
def create_workspace(
    session: SessionDep, current_user: CurrentUser, workspace_in: WorkspaceCreate
) -> Any:
    """Create a workspace. The creator becomes its owner."""
    workspace = crud.create_workspace(
        session=session, workspace_in=workspace_in, owner_id=current_user.id
    )
    return _workspace_public(workspace.members[0])


@router.get("/", response_model=WorkspacesPublic)
def list_workspaces(
    session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    """The workspaces the current user belongs to."""
    memberships, count = crud.get_memberships_for_user(
        session=session, user_id=current_user.id, skip=skip, limit=limit
    )
    return WorkspacesPublic(
        data=[_workspace_public(m) for m in memberships], count=count
    )


@router.get("/{workspace_id}", response_model=WorkspacePublic)
def get_workspace(member: CurrentMember) -> Any:
    return _workspace_public(member)


@router.patch("/{workspace_id}", response_model=WorkspacePublic)
def update_workspace(
    session: SessionDep, member: CurrentMember, workspace_in: WorkspaceUpdate
) -> Any:
    """Rename the workspace or change its slug."""
    require_manager(member, "update the workspace")
    assert member.workspace is not None
    crud.update_workspace(
        session=session, workspace=member.workspace, workspace_in=workspace_in
    )
    return _workspace_public(member)


@router.delete("/{workspace_id}", response_model=Message)
def delete_workspace(session: SessionDep, member: CurrentMember) -> Any:
    """Delete the workspace with all its integrations and metrics."""
    _require_owner(member, "delete the workspace")
    assert member.workspace is not None
    crud.delete(session, member.workspace)
    return Message(message="Workspace deleted successfully")


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/members", response_model=WorkspaceMembersPublic)
def list_members(session: SessionDep, member: CurrentMember) -> Any:
    members = crud.get_members(session=session, workspace_id=member.workspace_id)
    return WorkspaceMembersPublic(
        data=[_member_public(m) for m in members], count=len(members)
    )


@router.post("/{workspace_id}/members", response_model=WorkspaceMemberPublic)
def add_member(
    session: SessionDep, member: CurrentMember, member_in: WorkspaceMemberAdd
) -> Any:
    """Add an existing user, identified by id or email, to the workspace."""
    require_manager(member, "add members")
    if member_in.role == WorkspaceRole.owner:
        _require_owner(member, "add other owners")

    user = _find_user(session, member_in)
    if crud.get_member(
        session=session, workspace_id=member.workspace_id, user_id=user.id
    ):
        raise HTTPException(
            status_code=409, detail="User is already a member of this workspace"
        )
    new_member = crud.add_member(
        session=session,
        workspace_id=member.workspace_id,
        user_id=user.id,
        role=member_in.role,
    )
    return _member_public(new_member)


@router.patch("/{workspace_id}/members/{user_id}", response_model=WorkspaceMemberPublic)
def update_member(
    session: SessionDep,
    member: CurrentMember,
    user_id: uuid.UUID,
    member_in: WorkspaceMemberUpdate,
) -> Any:
    """Change a member's role."""
    _require_owner(member, "change roles")
    target = _get_target_member(session, member.workspace_id, user_id)
    if member_in.role != WorkspaceRole.owner:
        _keep_an_owner(session, target, "demote")
    target = crud.update_member_role(
        session=session, member=target, role=member_in.role
    )
    return _member_public(target)


@router.delete("/{workspace_id}/members/{user_id}", response_model=Message)
def remove_member(
    session: SessionDep, member: CurrentMember, user_id: uuid.UUID
) -> Any:
    """Remove a member. Anyone can leave; owners and admins can remove others."""
    target = _get_target_member(session, member.workspace_id, user_id)
    if target.user_id != member.user_id:
        require_manager(member, "remove members")
        if target.role == WorkspaceRole.owner:
            _require_owner(member, "remove other owners")
    _keep_an_owner(session, target, "remove")
    crud.delete(session, target)
    return Message(message="Member removed successfully")
