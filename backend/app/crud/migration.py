import uuid
from collections.abc import Sequence

from sqlmodel import Session, col, select

from app.models.migration import Migration, MigrationStatus

UNFINISHED_STATUSES = (MigrationStatus.pending, MigrationStatus.running)


def get_migrations(
    *, session: Session, workspace_id: uuid.UUID, limit: int = 20
) -> Sequence[Migration]:
    """The workspace's latest migrations, newest first."""
    statement = (
        select(Migration)
        .where(Migration.workspace_id == workspace_id)
        .order_by(col(Migration.created_at).desc())
        .limit(limit)
    )
    return session.exec(statement).all()


def has_unfinished_migration(*, session: Session, workspace_id: uuid.UUID) -> bool:
    statement = select(Migration.id).where(
        Migration.workspace_id == workspace_id,
        col(Migration.status).in_(UNFINISHED_STATUSES),
    )
    return session.exec(statement).first() is not None
