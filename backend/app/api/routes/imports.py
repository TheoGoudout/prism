"""
Importing history exported from another social media tool (Hootsuite, Sprout
Social, Buffer, Metricool, Later, Agorapulse…) into a connected account.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app import crud
from app.api.deps import CurrentMember, SessionDep, require_manager
from app.imports.reading import ImportFileError
from app.models.imports import ImportResult, ImportSource, PlatformAccountPublic
from app.services.imports import import_file

MAX_FILE_BYTES = 10 * 1024 * 1024

router = APIRouter(prefix="/workspaces/{workspace_id}/imports", tags=["imports"])


@router.get("/accounts", response_model=list[PlatformAccountPublic])
def list_import_accounts(session: SessionDep, member: CurrentMember) -> Any:
    """The accounts data can be imported into: those found by a sync."""
    accounts = crud.get_accounts_for_workspace(
        session=session, workspace_id=member.workspace_id
    )
    return sorted(accounts, key=lambda a: (a.platform.value, a.name.lower()))


@router.post("/", response_model=ImportResult)
def import_data(
    session: SessionDep,
    member: CurrentMember,
    platform_account_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File(description="A CSV export")],
    source: Annotated[
        ImportSource | None,
        Form(description="The tool the file comes from; detected if omitted"),
    ] = None,
) -> Any:
    """
    Import a CSV exported from another tool: per-post metrics or daily
    account metrics, into one of the workspace's accounts. Values the file
    doesn't have never erase stored ones, and importing the same file again
    updates rather than duplicates.
    """
    require_manager(member, "import data")
    account = next(
        (
            a
            for a in crud.get_accounts_for_workspace(
                session=session, workspace_id=member.workspace_id
            )
            if a.id == platform_account_id
        ),
        None,
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
        result = import_file(session, account, data, source)
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
