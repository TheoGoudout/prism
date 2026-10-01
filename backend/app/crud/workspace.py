import re
import uuid
from collections.abc import Sequence

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.crud.common import save
from app.models.workspace import (
    Workspace,
    WorkspaceCreate,
    WorkspaceMember,
    WorkspaceRole,
    WorkspaceUpdate,
)


def _slugify(text: str) -> str:
    """Convert a workspace name (or requested slug) into a URL-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "workspace"


def _unique_slug(session: Session, text: str) -> str:
    """Slugify ``text``, appending a counter if the slug is already taken."""
    base = slug = _slugify(text)
    counter = 1
    while session.exec(select(Workspace).where(Workspace.slug == slug)).first():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def create_workspace(
    *, session: Session, workspace_in: WorkspaceCreate, owner_id: uuid.UUID
) -> Workspace:
    """Create a workspace with ``owner_id`` as its first owner."""
    slug = _unique_slug(session, workspace_in.slug or workspace_in.name)
    workspace = Workspace(name=workspace_in.name, slug=slug)
    workspace.members.append(
        WorkspaceMember(user_id=owner_id, role=WorkspaceRole.owner)
    )
    return save(session, workspace)


def get_workspace(*, session: Session, workspace_id: uuid.UUID) -> Workspace | None:
    return session.get(Workspace, workspace_id)


def get_memberships_for_user(
    *, session: Session, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> tuple[Sequence[WorkspaceMember], int]:
    """The user's memberships (oldest workspace first) and their total count."""
    is_member = WorkspaceMember.user_id == user_id
    statement = (
        select(WorkspaceMember)
        .join(Workspace)
        .where(is_member)
        .order_by(col(Workspace.created_at))
        .offset(skip)
        .limit(limit)
    )
    count_statement = select(func.count()).select_from(WorkspaceMember).where(is_member)
    return session.exec(statement).all(), session.exec(count_statement).one()


def update_workspace(
    *, session: Session, workspace: Workspace, workspace_in: WorkspaceUpdate
) -> Workspace:
    if workspace_in.name is not None:
        workspace.name = workspace_in.name
    if workspace_in.slug is not None and workspace_in.slug != workspace.slug:
        workspace.slug = _unique_slug(session, workspace_in.slug)
    return save(session, workspace)


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


def count_owners(*, session: Session, workspace_id: uuid.UUID) -> int:
    statement = (
        select(func.count())
        .select_from(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == WorkspaceRole.owner,
        )
    )
    return session.exec(statement).one()


def add_member(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    role: WorkspaceRole,
) -> WorkspaceMember:
    member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
    return save(session, member)


def update_member_role(
    *, session: Session, member: WorkspaceMember, role: WorkspaceRole
) -> WorkspaceMember:
    member.role = role
    return save(session, member)
