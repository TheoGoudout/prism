"""
Migrating history from another social media tool: through its API (Sprout
Social, Metricool) or by uploading a CSV export (any supported tool).
"""

import uuid
from datetime import date as date_type
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, Date
from sqlalchemy import DateTime as SADateTime
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel

from app.models.common import get_datetime_utc
from app.models.integration import Platform

# ---------------------------------------------------------------------------
# CSV uploads
# ---------------------------------------------------------------------------


class ExportFormat(StrEnum):
    """The tool a CSV was exported from; each names its columns its own way."""

    hootsuite = "hootsuite"
    sprout_social = "sprout_social"
    buffer = "buffer"
    metricool = "metricool"
    later = "later"
    agorapulse = "agorapulse"
    # Any other CSV whose headers use common names (Date, Impressions, …)
    csv = "csv"


class DataKind(StrEnum):
    """What a file holds: one row per post, or one row per day for the account."""

    posts = "posts"
    daily_metrics = "daily_metrics"


class UploadResult(SQLModel):
    """What an uploaded export held, and what was stored."""

    format: ExportFormat
    kind: DataKind
    platform_account_id: uuid.UUID
    rows_read: int
    created: int
    updated: int
    # Rows for another network, in an export covering several networks
    skipped_other_networks: int
    # Rows that couldn't be read; the first few are described in errors
    rejected: int
    errors: list[str]
    date_from: date_type | None = None
    date_to: date_type | None = None


class PlatformAccountPublic(SQLModel):
    """An account (page, profile, property) history can be migrated into."""

    id: uuid.UUID
    integration_id: uuid.UUID
    platform: Platform
    name: str
    account_type: str | None = None


# ---------------------------------------------------------------------------
# API migrations
# ---------------------------------------------------------------------------


class MigrationSource(StrEnum):
    """The tools Prism can migrate from through their API."""

    sprout_social = "sprout_social"
    metricool = "metricool"


class MigrationStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class SourceCredentials(SQLModel):
    """
    Access to the source tool's API. Sprout Social: an API token. Metricool:
    the user token (X-Mc-Auth) and the user ID, and optionally the ID of one
    brand (blogId) when the account requires it.
    """

    api_token: str = Field(min_length=1, max_length=2048)
    user_id: str | None = Field(default=None, max_length=64)
    blog_id: str | None = Field(default=None, max_length=64)


class RemoteProfile(SQLModel):
    """A profile in the source tool, e.g. a Facebook page in a Metricool brand."""

    # Opaque to clients: whatever the source needs to fetch the profile
    id: str
    name: str
    network: str
    # None for a network Prism doesn't support (e.g. YouTube)
    platform: Platform | None = None
    # The network's own ID, when the tool gives it
    native_id: str | None = None
    # The workspace account it most likely is
    suggested_account_id: uuid.UUID | None = None


class ProfileMapping(SQLModel):
    remote_profile_id: str = Field(max_length=255)
    platform_account_id: uuid.UUID


class MigrationCreate(SQLModel):
    credentials: SourceCredentials
    profiles: list[ProfileMapping] = Field(min_length=1, max_length=100)
    # How far back to migrate; up to today
    date_from: date_type


class ProfileProgress(SQLModel):
    """What was migrated for one profile."""

    remote_profile_id: str
    name: str
    platform: Platform
    platform_account_id: uuid.UUID
    done: bool = False
    posts: int = 0
    days: int = 0
    errors: list[str] = []


class Migration(SQLModel, table=True):
    """One run of migrating history from another tool's API."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(
        foreign_key="workspace.id", nullable=False, ondelete="CASCADE", index=True
    )
    created_by_id: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )
    source: MigrationSource
    status: MigrationStatus = Field(default=MigrationStatus.pending)
    # SourceCredentials, encrypted; erased once the migration finishes
    credentials_encrypted: str | None = None
    date_from: date_type = Field(sa_column=Column(Date, nullable=False))
    date_to: date_type = Field(sa_column=Column(Date, nullable=False))
    # A ProfileProgress per migrated profile
    profiles: list[dict[str, Any]] = Field(default=[], sa_type=JSON)
    error: str | None = Field(default=None, max_length=1024)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(SADateTime(timezone=True), nullable=True),
    )
    completed_at: datetime | None = Field(
        default=None, sa_column=Column(SADateTime(timezone=True), nullable=True)
    )


class MigrationPublic(SQLModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    source: MigrationSource
    status: MigrationStatus
    date_from: date_type
    date_to: date_type
    profiles: list[ProfileProgress]
    error: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
