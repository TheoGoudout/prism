"""Importing an exported file into one of the workspace's accounts."""

from sqlmodel import Session

from app import crud
from app.imports.parser import date_range, parse_export
from app.models.imports import ImportKind, ImportResult, ImportSource
from app.models.integration import PlatformAccount


def import_file(
    session: Session,
    account: PlatformAccount,
    data: bytes,
    source: ImportSource | None = None,
) -> ImportResult:
    """
    Parse the file and store its posts or daily metrics in ``account``.

    Raises ImportFileError when the file can't be read at all.
    """
    parsed = parse_export(data, platform=account.platform, source=source)
    if parsed.kind is ImportKind.posts:
        created, updated = crud.merge_imported_posts(
            session=session,
            platform_account_id=account.id,
            posts=parsed.posts,
            source=parsed.source.value,
        )
    else:
        created, updated = crud.merge_imported_snapshots(
            session=session,
            platform_account_id=account.id,
            snapshots=parsed.snapshots,
            source=parsed.source.value,
        )
    date_from, date_to = date_range(parsed)
    return ImportResult(
        source=parsed.source,
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
