"""Migrating history from another tool into the workspace's accounts."""

import json
import logging
import uuid
from collections.abc import Sequence
from datetime import date

from sqlmodel import Session

from app import crud
from app.core.encryption import decrypt_token, encrypt_token
from app.migrate.files.parser import date_range, parse_export
from app.migrate.sources import SOURCES, SourceAuthError
from app.migrate.sources.base import describe_error
from app.models.common import get_datetime_utc
from app.models.integration import PlatformAccount
from app.models.migration import (
    DataKind,
    ExportFormat,
    Migration,
    MigrationSource,
    MigrationStatus,
    ProfileMapping,
    ProfileProgress,
    RemoteProfile,
    SourceCredentials,
    UploadResult,
)

logger = logging.getLogger(__name__)

# Errors kept per profile; more would only be noise
MAX_PROFILE_ERRORS = 10


# ---------------------------------------------------------------------------
# CSV uploads
# ---------------------------------------------------------------------------


def import_file(
    session: Session,
    account: PlatformAccount,
    data: bytes,
    export_format: ExportFormat | None = None,
) -> UploadResult:
    """
    Parse an exported file and store its posts or daily metrics in ``account``,
    in one transaction.

    Raises ImportFileError when the file can't be read at all.
    """
    parsed = parse_export(data, platform=account.platform, export_format=export_format)
    if parsed.kind is DataKind.posts:
        created, updated = crud.merge_imported_posts(
            session=session,
            platform_account_id=account.id,
            posts=parsed.posts,
            source=parsed.export_format.value,
        )
    else:
        created, updated = crud.merge_imported_snapshots(
            session=session,
            platform_account_id=account.id,
            snapshots=parsed.snapshots,
            source=parsed.export_format.value,
        )
    session.commit()
    date_from, date_to = date_range(parsed)
    return UploadResult(
        format=parsed.export_format,
        kind=parsed.kind,
        platform_account_id=account.id,
        rows_read=parsed.rows_read,
        created=created,
        updated=updated,
        skipped_other_networks=parsed.skipped_other_networks,
        rejected=parsed.rejected,
        errors=parsed.errors,
        date_from=date_from,
        date_to=date_to,
    )


# ---------------------------------------------------------------------------
# API migrations
# ---------------------------------------------------------------------------


def list_profiles(
    source: MigrationSource,
    credentials: SourceCredentials,
    accounts: Sequence[PlatformAccount],
) -> list[RemoteProfile]:
    """
    The source's profiles, each with the workspace account it most likely
    is. Raises SourceAuthError if the credentials are rejected.
    """
    profiles = SOURCES[source].list_profiles(credentials)
    for profile in profiles:
        profile.suggested_account_id = suggest_account(profile, accounts)
    return profiles


def suggest_account(
    profile: RemoteProfile, accounts: Sequence[PlatformAccount]
) -> uuid.UUID | None:
    """
    The account with the same network ID; else the one with the same name;
    else the platform's only account.
    """
    candidates = [a for a in accounts if a.platform == profile.platform]
    for matches in (
        lambda a: profile.native_id is not None and a.external_id == profile.native_id,
        lambda a: a.name.casefold() in profile.name.casefold(),
    ):
        found = [a for a in candidates if matches(a)]
        if len(found) == 1:
            return found[0].id
    return candidates[0].id if len(candidates) == 1 else None


def create_migration(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    source: MigrationSource,
    credentials: SourceCredentials,
    profiles: list[RemoteProfile],
    mappings: list[ProfileMapping],
    accounts: Sequence[PlatformAccount],
    date_from: date,
) -> Migration:
    """
    A pending migration of the mapped profiles. Raises ValueError if a
    mapping names an unknown profile or account, or mixes platforms.
    """
    by_profile = {p.id: p for p in profiles}
    by_account = {a.id: a for a in accounts}
    progress = []
    for mapping in mappings:
        profile = by_profile.get(mapping.remote_profile_id)
        account = by_account.get(mapping.platform_account_id)
        if profile is None:
            raise ValueError(f"Unknown profile {mapping.remote_profile_id}")
        if account is None:
            raise ValueError(f"Unknown account {mapping.platform_account_id}")
        if profile.platform != account.platform:
            raise ValueError(
                f"{profile.name} is a {profile.network} profile: it can't be "
                f"migrated into a {account.platform.value} account"
            )
        progress.append(
            ProfileProgress(
                remote_profile_id=profile.id,
                name=profile.name,
                platform=account.platform,
                platform_account_id=account.id,
            ).model_dump(mode="json")
        )
    migration = Migration(
        workspace_id=workspace_id,
        created_by_id=user_id,
        source=source,
        credentials_encrypted=encrypt_token(credentials.model_dump_json()),
        date_from=date_from,
        date_to=get_datetime_utc().date(),
        profiles=progress,
    )
    return crud.save(session, migration)


def run(session: Session, migration: Migration) -> None:
    """
    Fetch every mapped profile from the source and store it. Each profile's
    data is committed with its progress, so a profile is either fully
    migrated and marked done, or not at all; one already done (by a run
    interrupted by a worker restart) is skipped.
    """
    if migration.credentials_encrypted is None:
        finish(session, migration, "The credentials are no longer available")
        return
    credentials = SourceCredentials.model_validate(
        json.loads(decrypt_token(migration.credentials_encrypted))
    )
    migration.status = MigrationStatus.running
    crud.save(session, migration)

    source = SOURCES[migration.source]
    progress = [ProfileProgress.model_validate(p) for p in migration.profiles]
    try:
        for item in progress:
            if item.done:
                continue
            profile = RemoteProfile(
                id=item.remote_profile_id,
                name=item.name,
                network=item.platform.value,
                platform=item.platform,
            )
            data = source.fetch(
                credentials, profile, migration.date_from, migration.date_to
            )
            item.posts = sum(
                crud.merge_imported_posts(
                    session=session,
                    platform_account_id=item.platform_account_id,
                    posts=data.posts,
                    source=migration.source.value,
                )
            )
            item.days = sum(
                crud.merge_imported_snapshots(
                    session=session,
                    platform_account_id=item.platform_account_id,
                    snapshots=data.snapshots,
                    source=migration.source.value,
                )
            )
            item.errors = data.errors[:MAX_PROFILE_ERRORS]
            item.done = True
            migration.profiles = [p.model_dump(mode="json") for p in progress]
            crud.save(session, migration)
    except Exception as exc:
        session.rollback()  # the failed profile's partial data
        if not isinstance(exc, SourceAuthError):
            logger.exception("Migration %s failed", migration.id)
        finish(session, migration, describe_error(exc))
        return
    finish(session, migration, None)


def finish(session: Session, migration: Migration, error: str | None) -> None:
    """Record the migration's outcome and forget the source's credentials."""
    migration.status = MigrationStatus.failed if error else MigrationStatus.completed
    migration.error = error[:1024] if error else None
    migration.completed_at = get_datetime_utc()
    # Only needed while running: don't keep access to the other tool
    migration.credentials_encrypted = None
    crud.save(session, migration)
