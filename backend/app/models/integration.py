import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.models.common import timestamp_field
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
    mailchimp = "mailchimp"
    klaviyo = "klaviyo"
    brevo = "brevo"


class IntegrationStatus(StrEnum):
    active = "active"
    expired = "expired"
    error = "error"
    disconnected = "disconnected"


# ---------------------------------------------------------------------------
# Database models
# ---------------------------------------------------------------------------


class Integration(SQLModel, table=True):
    """
    One connection between a workspace and a platform: through OAuth, or an
    API key for the platforms without OAuth (stored as the access token).
    """

    # Reconnecting an account updates its integration (see
    # app.crud.integration.upsert_integration) rather than adding another one
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "platform",
            "external_account_id",
            name="uq_integration_workspace_platform_account",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspace.id", nullable=False, ondelete="CASCADE", index=True
    )
    platform: Platform
    status: IntegrationStatus = Field(default=IntegrationStatus.active)

    # Encrypted OAuth tokens (or API key) — never exposed via the API
    access_token_encrypted: str | None = Field(default=None)
    refresh_token_encrypted: str | None = Field(default=None)
    token_expires_at: datetime | None = timestamp_field()

    # External account snapshot (cached at connect time)
    external_account_id: str = Field(max_length=255)
    external_account_name: str = Field(max_length=255)
    # Meta CDN URLs carry long signed query strings
    external_account_avatar: str | None = Field(default=None, max_length=2048)

    # Sync state
    last_synced_at: datetime | None = timestamp_field()
    sync_error: str | None = Field(default=None, max_length=1024)
    # A follow-up sync on top of the nightly one, while recent posts are
    # getting engagement (see app.services.sync_schedule); None if none is due
    next_sync_at: datetime | None = timestamp_field()

    created_at: datetime | None = timestamp_field(now=True)

    workspace: Workspace | None = Relationship(back_populates="integrations")
    accounts: list[PlatformAccount] = Relationship(
        back_populates="integration",
        cascade_delete=True,
        sa_relationship_kwargs={"order_by": "PlatformAccount.name"},
    )


class PlatformAccount(SQLModel, table=True):
    """
    A specific account/page/profile within an integration.
    A single Facebook OAuth connection may expose multiple Pages.
    """

    __tablename__ = "platformaccount"
    __table_args__ = (
        UniqueConstraint(
            "integration_id",
            "external_id",
            name="uq_platformaccount_integration_external_id",
        ),
    )

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
    # Whether the dashboards show this account. New accounts are shown; users
    # can hide some, e.g. the Facebook Pages a workspace isn't about.
    is_active: bool = Field(default=True)
    created_at: datetime | None = timestamp_field(now=True)

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


class PlatformAccountPublic(SQLModel):
    id: uuid.UUID
    integration_id: uuid.UUID
    platform: Platform
    external_id: str
    name: str
    avatar_url: str | None = None
    account_type: str | None = None
    is_active: bool


class PlatformAccountUpdate(SQLModel):
    """Show (True) or hide (False) the account in the workspace's dashboards."""

    is_active: bool


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
    # The pages / profiles / properties found by its syncs, shown or not
    accounts: list[PlatformAccountPublic] = []


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


class ApiKeyConnect(SQLModel):
    """Connect a platform that is authorized with an API key, not OAuth."""

    api_key: str = Field(min_length=1, max_length=512)


class OAuthConnectResponse(SQLModel):
    """Where to send the user to authorize the platform."""

    authorization_url: str
