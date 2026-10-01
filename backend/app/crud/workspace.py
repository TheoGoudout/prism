import re
import uuid
from collections.abc import Sequence

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.workspace import (
    Workspace,
    WorkspaceCreate,
    WorkspaceMember,
    WorkspaceMemberAdd,
    WorkspaceMemberUpdate,
    WorkspaceRole,
    WorkspaceUpdate,
)


def _slugify(name: str) -> str:
    """Convert a workspace name into a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "workspace"


def _unique_slug(session: Session, base: str) -> str:
    """Ensure the slug is unique, appending a counter suffix if needed."""
    slug = base
    counter = 1
    while session.exec(select(Workspace).where(Workspace.slug == slug)).first():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def create_workspace(
    *, session: Session, workspace_in: WorkspaceCreate, owner_id: uuid.UUID
) -> Workspace:
    if workspace_in.slug:
        slug = workspace_in.slug.lower()
    else:
        slug = _slugify(workspace_in.name)
    slug = _unique_slug(session, slug)

    workspace = Workspace(name=workspace_in.name, slug=slug)
    session.add(workspace)
    session.flush()  # populate workspace.id before creating the member

    member = WorkspaceMember(
        workspace_id=workspace.id, user_id=owner_id, role=WorkspaceRole.owner
    )
    session.add(member)
    session.commit()
    session.refresh(workspace)
    return workspace


def get_workspace(*, session: Session, workspace_id: uuid.UUID) -> Workspace | None:
    return session.get(Workspace, workspace_id)


def get_workspaces_for_user(
    *, session: Session, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> tuple[Sequence[Workspace], int]:
    """Return workspaces the user is a member of, with total count."""
    on_clause = col(WorkspaceMember.workspace_id) == col(Workspace.id)
    statement = (
        select(Workspace)
        .join(WorkspaceMember, on_clause)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(col(Workspace.created_at))
        .offset(skip)
        .limit(limit)
    )
    workspaces = session.exec(statement).all()

    count_statement = (
        select(func.count())
        .select_from(Workspace)
        .join(WorkspaceMember, on_clause)
        .where(WorkspaceMember.user_id == user_id)
    )
    count = session.exec(count_statement).one()
    return workspaces, count


def update_workspace(
    *, session: Session, workspace: Workspace, workspace_in: WorkspaceUpdate
) -> Workspace:
    update_data = workspace_in.model_dump(exclude_unset=True)
    if "slug" in update_data and update_data["slug"]:
        update_data["slug"] = update_data["slug"].lower()
    workspace.sqlmodel_update(update_data)
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    return workspace


def delete_workspace(*, session: Session, workspace: Workspace) -> None:
    session.delete(workspace)
    session.commit()


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


def get_member(
    *, session: Session, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> WorkspaceMember | None:
    return session.get(WorkspaceMember, (workspace_id, user_id))


def get_members(
    *, session: Session, workspace_id: uuid.UUID
) -> Sequence[WorkspaceMember]:
    statement = select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace_id
    )
    return session.exec(statement).all()


def add_member(
    *, session: Session, workspace_id: uuid.UUID, member_in: WorkspaceMemberAdd
) -> WorkspaceMember:
    if member_in.user_id is None:
        raise ValueError("add_member requires a resolved user_id")
    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=member_in.user_id,
        role=member_in.role,
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def update_member(
    *,
    session: Session,
    member: WorkspaceMember,
    member_in: WorkspaceMemberUpdate,
) -> WorkspaceMember:
    member.role = member_in.role
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def remove_member(*, session: Session, member: WorkspaceMember) -> None:
    session.delete(member)
    session.commit()
