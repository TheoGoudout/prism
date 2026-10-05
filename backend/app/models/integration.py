import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel

from app.models.common import get_datetime_utc
from app.models.workspace import Workspace

if TYPE_CHECKING:
    from app.models.metrics import MetricSnapshot, Post


class Platform(StrEnum):
    facebook = "facebook"
    instagram = "instagram"
    twitter = "twitter"
    linkedin = "linkedin"
    tiktok = "tiktok"
    google_analytics = "google_analytics"


class IntegrationStatus(StrEnum):
    active = "active"
    expired = "expired"
    error = "error"
    disconnected = "disconnected"


# ---------------------------------------------------------------------------
# Database models
# ---------------------------------------------------------------------------


class Integration(SQLModel, table=True):
    """One OAuth connection between a workspace and a social platform."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspace.id", nullable=False, ondelete="CASCADE", index=True
    )
    platform: Platform
    status: IntegrationStatus = Field(default=IntegrationStatus.active)

    # Encrypted OAuth tokens — never exposed via the API
    access_token_encrypted: str | None = Field(default=None)
    refresh_token_encrypted: str | None = Field(default=None)
    token_expires_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )

    # External account snapshot (cached at connect time)
    external_account_id: str = Field(max_length=255)
    external_account_name: str = Field(max_length=255)
    # Meta CDN URLs carry long signed query strings
    external_account_avatar: str | None = Field(default=None, max_length=2048)

    # Sync state
    last_synced_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    sync_error: str | None = Field(default=None, max_length=1024)
    # A follow-up sync on top of the nightly one, while recent posts are
    # getting engagement (see app.services.sync_schedule); None if none is due
    next_sync_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )

    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),
    )

    workspace: Workspace | None = Relationship(back_populates="integrations")
    accounts: list[PlatformAccount] = Relationship(
        back_populates="integration", cascade_delete=True
    )


class PlatformAccount(SQLModel, table=True):
    """
    A specific account/page/profile within an integration.
    A single Facebook OAuth connection may expose multiple Pages.
    """

    __tablename__ = "platformaccount"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    integration_id: uuid.UUID = Field(
        foreign_key="integration.id", nullable=False, ondelete="CASCADE", index=True
    )
    workspace_id: uuid.UUID = Field(
        foreign_key="workspace.id", nullable=False, ondelete="CASCADE", index=True
    )
    platform: Platform
    external_id: str = Field(max_length=255, index=True)
    name: str = Field(max_length=255)
    avatar_url: str | None = Field(default=None, max_length=2048)
    # e.g. "page", "profile", "business_account", "property"
    account_type: str | None = Field(default=None, max_length=64)
    is_active: bool = Field(default=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),
    )

    integration: Integration | None = Relationship(back_populates="accounts")
    workspace: Workspace | None = Relationship(back_populates="platform_accounts")
    metric_snapshots: list[MetricSnapshot] = Relationship(
        back_populates="platform_account", cascade_delete=True
    )
    posts: list[Post] = Relationship(
        back_populates="platform_account", cascade_delete=True
    )


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class IntegrationPublic(SQLModel):
    """Safe representation — never includes raw or encrypted tokens."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    platform: Platform
    status: IntegrationStatus
    external_account_id: str
    external_account_name: str
    external_account_avatar: str | None = None
    last_synced_at: datetime | None = None
    sync_error: str | None = None
    created_at: datetime | None = None


class IntegrationCreate(SQLModel):
    """Internal use only (called from OAuth callback, not directly by users)."""

    platform: Platform
    workspace_id: uuid.UUID
    access_token: str
    refresh_token: str | None = None
    token_expires_at: datetime | None = None
    external_account_id: str
    external_account_name: str
    external_account_avatar: str | None = None


class OAuthConnectResponse(SQLModel):
    """Where to send the user to authorize the platform."""

    authorization_url: str
