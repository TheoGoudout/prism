import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import EmailStr
from sqlmodel import Field, Relationship, SQLModel

from app.models.common import timestamp_field
from app.models.user import User

if TYPE_CHECKING:
    from app.models.integration import Integration, PlatformAccount


class WorkspaceRole(StrEnum):
    owner = "owner"  # full control, including deleting the workspace
    admin = "admin"  # manages integrations and members
    viewer = "viewer"  # read-only

    @property
    def can_manage(self) -> bool:
        """Whether this role may manage integrations, members and settings."""
        return self in (WorkspaceRole.owner, WorkspaceRole.admin)


# ---------------------------------------------------------------------------
# Database models
# ---------------------------------------------------------------------------


class Workspace(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(unique=True, index=True, max_length=100)
    created_at: datetime | None = timestamp_field(now=True)
    members: list[WorkspaceMember] = Relationship(
        back_populates="workspace", cascade_delete=True
    )
    integrations: list[Integration] = Relationship(
        back_populates="workspace", cascade_delete=True
    )
    platform_accounts: list[PlatformAccount] = Relationship(
        back_populates="workspace", cascade_delete=True
    )


class WorkspaceMember(SQLModel, table=True):
    __tablename__ = "workspacemember"

    workspace_id: uuid.UUID = Field(
        foreign_key="workspace.id", primary_key=True, ondelete="CASCADE"
    )
    user_id: uuid.UUID = Field(
        foreign_key="user.id", primary_key=True, ondelete="CASCADE"
    )
    role: WorkspaceRole = Field(default=WorkspaceRole.viewer)
    created_at: datetime | None = timestamp_field(now=True)

    workspace: Workspace | None = Relationship(back_populates="members")
    user: User | None = Relationship(back_populates="workspace_memberships")


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class WorkspaceCreate(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=100)


class WorkspaceUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=100)


class WorkspacePublic(SQLModel):
    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime | None = None
    # Role of the requesting user in this workspace
    role: WorkspaceRole


class WorkspaceMemberPublic(SQLModel):
    user_id: uuid.UUID
    role: WorkspaceRole
    created_at: datetime | None = None
    # Flattened user info for convenience
    user_email: str
    user_full_name: str | None = None


class WorkspaceMemberAdd(SQLModel):
    """An existing user to add, identified by the email they signed up with."""

    email: EmailStr = Field(max_length=255)
    role: WorkspaceRole = WorkspaceRole.viewer


class WorkspaceMemberUpdate(SQLModel):
    role: WorkspaceRole
