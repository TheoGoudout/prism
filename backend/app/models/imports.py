import uuid
from datetime import date
from enum import StrEnum

from sqlmodel import SQLModel

from app.models.integration import Platform


class ImportSource(StrEnum):
    """The tool a file was exported from; each names its columns its own way."""

    hootsuite = "hootsuite"
    sprout_social = "sprout_social"
    buffer = "buffer"
    metricool = "metricool"
    later = "later"
    agorapulse = "agorapulse"
    # Any other CSV whose headers use common names (Date, Impressions, …)
    csv = "csv"


class ImportKind(StrEnum):
    """What a file holds: one row per post, or one row per day for the account."""

    posts = "posts"
    daily_metrics = "daily_metrics"


class ImportResult(SQLModel):
    """What an import read from the file and stored."""

    source: ImportSource
    kind: ImportKind
    platform_account_id: uuid.UUID
    rows_read: int
    created: int
    updated: int
    # Rows for another network, in an export covering several networks
    skipped_other_networks: int
    # Rows that couldn't be read; the first few are described in errors
    rejected: int
    errors: list[str]
    date_from: date | None = None
    date_to: date | None = None


class PlatformAccountPublic(SQLModel):
    """An account (page, profile, property) data can be imported into."""

    id: uuid.UUID
    integration_id: uuid.UUID
    platform: Platform
    name: str
    account_type: str | None = None
