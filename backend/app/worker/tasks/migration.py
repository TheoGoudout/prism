"""Migration tasks — fetch a workspace's history from another tool's API."""

import logging
import uuid
from typing import Any

from sqlmodel import Session

from app.core.db import engine
from app.crud.migration import UNFINISHED_STATUSES
from app.models.migration import Migration
from app.services import migration as migration_service
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.worker.tasks.migration.run_migration")
def run_migration(migration_id: str) -> dict[str, Any]:
    """Run one migration; failures are recorded on it, not retried."""
    with Session(engine) as session:
        migration = session.get(Migration, uuid.UUID(migration_id))
        if migration is None:
            logger.warning("run_migration: migration %s not found", migration_id)
            return {"status": "not_found", "migration_id": migration_id}
        # `running` too: a task redelivered after a worker crash resumes it
        if migration.status not in UNFINISHED_STATUSES:
            return {"status": "skipped", "reason": migration.status.value}
        migration_service.run(session, migration)
        return {"status": migration.status.value, "migration_id": migration_id}
