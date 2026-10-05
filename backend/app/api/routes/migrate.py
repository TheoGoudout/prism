"""
Migrating history from another social media tool into the workspace's
accounts: through the tool's API (Sprout Social, Metricool), run in the
background, or by uploading a CSV export (any supported tool).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile, status

from app import crud
from app.api.deps import CurrentMember, SessionDep, require_manager
from app.migrate.files.reading import ImportFileError
from app.migrate.sources import SourceAuthError
from app.models.migration import (
    ExportFormat,
    MigrationCreate,
    MigrationPublic,
    MigrationSource,
    PlatformAccountPublic,
    RemoteProfile,
    SourceCredentials,
    UploadResult,
)
from app.services import migration as migration_service
from app.worker.tasks import migration as migration_tasks

MAX_FILE_BYTES = 10 * 1024 * 1024

router = APIRouter(prefix="/workspaces/{workspace_id}/migrate", tags=["migrate"])


def _accounts(session: SessionDep, member: CurrentMember) -> list[Any]:
    accounts = crud.get_accounts_for_workspace(
        session=session, workspace_id=member.workspace_id
    )
    return sorted(accounts, key=lambda a: (a.platform.value, a.name.lower()))


def _list_profiles(
    source: MigrationSource,
    credentials: SourceCredentials,
    accounts: list[Any],
) -> list[RemoteProfile]:
    try:
        return migration_service.list_profiles(source, credentials, accounts)
    except (SourceAuthError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Couldn't reach {source.value.replace('_', ' ').title()}. "
            "Please try again in a moment.",
        )


@router.get("/accounts", response_model=list[PlatformAccountPublic])
def list_migration_accounts(session: SessionDep, member: CurrentMember) -> Any:
    """The accounts history can be migrated into: those found by a sync."""
    return _accounts(session, member)


@router.post("/upload", response_model=UploadResult)
def upload_export(
    session: SessionDep,
    member: CurrentMember,
    platform_account_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File(description="A CSV export")],
    export_format: Annotated[
        ExportFormat | None,
        Form(description="The tool the file comes from; detected if omitted"),
    ] = None,
) -> Any:
    """
    Import a CSV exported from another tool: per-post metrics or daily
    account metrics, into one of the workspace's accounts. Values the file
    doesn't have never erase stored ones, and uploading the same file again
    updates rather than duplicates.
    """
    require_manager(member, "migrate data")
    account = next(
        (a for a in _accounts(session, member) if a.id == platform_account_id), None
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    data = file.file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The file is larger than 10 MB. Export a shorter date range.",
        )
    try:
        result = migration_service.import_file(session, account, data, export_format)
    except ImportFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )
    if result.created + result.updated == 0 and result.rejected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No row could be imported. " + " ".join(result.errors[:3]),
        )
    return result


@router.get("/runs", response_model=list[MigrationPublic])
def list_migrations(session: SessionDep, member: CurrentMember) -> Any:
    """The workspace's latest API migrations, newest first."""
    return crud.get_migrations(session=session, workspace_id=member.workspace_id)


@router.post("/{source}/profiles", response_model=list[RemoteProfile])
def list_source_profiles(
    session: SessionDep,
    member: CurrentMember,
    source: MigrationSource,
    credentials: Annotated[SourceCredentials, Body()],
) -> Any:
    """
    Check the credentials and list the source's profiles, each with the
    workspace account it most likely is.
    """
    require_manager(member, "migrate data")
    return _list_profiles(source, credentials, _accounts(session, member))


@router.post(
    "/{source}",
    response_model=MigrationPublic,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_migration(
    session: SessionDep,
    member: CurrentMember,
    source: MigrationSource,
    migration_in: MigrationCreate,
) -> Any:
    """
    Migrate the mapped profiles' daily metrics and posts since ``date_from``,
    in the background. The credentials are kept, encrypted, only until the
    migration finishes.
    """
    require_manager(member, "migrate data")
    if crud.has_unfinished_migration(session=session, workspace_id=member.workspace_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A migration is already running for this workspace",
        )
    accounts = _accounts(session, member)
    profiles = _list_profiles(source, migration_in.credentials, accounts)
    try:
        migration = migration_service.create_migration(
            session,
            workspace_id=member.workspace_id,
            user_id=member.user_id,
            source=source,
            credentials=migration_in.credentials,
            profiles=profiles,
            mappings=migration_in.profiles,
            accounts=accounts,
            date_from=migration_in.date_from,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )
    migration_tasks.run_migration.delay(str(migration.id))
    return migration
