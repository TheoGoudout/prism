"""
Sync tasks — fetch fresh metrics from the connected platforms.

`sync_integration` syncs one integration and records the outcome on it
(active / error / expired), then schedules a follow-up sync while its recent
posts are getting engagement (see app.services.sync_schedule).
`sync_all_active_integrations` runs nightly and enqueues one `sync_integration`
per integration; `sync_due_integrations` runs every few minutes and enqueues
the due follow-up syncs.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

import httpx
from sqlmodel import Session, col, select

from app import crud
from app.core.db import engine
from app.integrations.oauth import registry
from app.integrations.platforms import SYNC_FUNCTIONS
from app.integrations.tokens import TokenExpiredError, ensure_fresh_token
from app.models.common import get_datetime_utc
from app.models.integration import Integration, IntegrationStatus
from app.services import sync_schedule
from app.worker.celery_app import celery_app, enqueue

logger = logging.getLogger(__name__)

# Statuses picked up by the scheduled sync. `error` is included so a transient
# failure doesn't stop an integration from syncing for good; `expired` and
# `disconnected` integrations need the user to reconnect first.
SYNCABLE_STATUSES = (IntegrationStatus.active, IntegrationStatus.error)

RECONNECT_MESSAGE = "The platform rejected our access token. Please reconnect."


def _is_auth_error(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401


def _reconnect(exc: Exception) -> str:
    """Why the user must reconnect, for an expired or rejected token."""
    return str(exc) if isinstance(exc, TokenExpiredError) else RECONNECT_MESSAGE


def _sync(session: Session, integration: Integration) -> datetime | None:
    """
    Fetch the integration's data and store it, all in one transaction with
    its new status: a failing sync stores nothing. Returns when the next
    follow-up sync is due.
    """
    ensure_fresh_token(session=session, integration=integration)
    access_token = crud.get_access_token(integration)
    if not access_token:
        raise TokenExpiredError("No access token stored. Please reconnect.")
    SYNC_FUNCTIONS[integration.platform](session, integration, access_token)
    next_sync_at = sync_schedule.schedule_next_sync(
        session, integration, get_datetime_utc()
    )
    crud.mark_integration_synced(session=session, integration=integration)
    return next_sync_at


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="app.worker.tasks.sync.sync_integration",
)
def sync_integration(self: Any, integration_id: str) -> dict[str, Any]:
    """
    Sync one integration, refreshing its access token first if it is about to
    expire. Transient errors (network, rate limits) are retried up to 3 times.
    """
    with Session(engine) as session:
        integration = crud.get_integration(
            session=session, integration_id=uuid.UUID(integration_id)
        )
        if integration is None:
            logger.warning("sync_integration: integration %s not found", integration_id)
            return {"status": "not_found", "integration_id": integration_id}
        if integration.status not in SYNCABLE_STATUSES:
            return {"status": "skipped", "reason": integration.status.value}
        if not registry.is_available(integration.platform):
            logger.warning(
                "sync_integration: skipping %s, the %s integration is not set up",
                integration_id,
                integration.platform.value,
            )
            return {"status": "skipped", "reason": "platform_unavailable"}

        try:
            next_sync_at = _sync(session, integration)
        except Exception as exc:
            # Drop the sync's partial writes; refreshed tokens are already saved
            session.rollback()
            if isinstance(exc, TokenExpiredError) or _is_auth_error(exc):
                # The user must reconnect: retrying won't help
                crud.mark_integration_expired(
                    session=session, integration=integration, error=_reconnect(exc)
                )
                return {"status": "expired", "integration_id": integration_id}
            logger.exception("sync_integration: error for %s", integration_id)
            crud.mark_integration_error(
                session=session, integration=integration, error=str(exc)
            )
            raise self.retry(exc=exc)

        logger.info(
            "sync_integration: OK for %s, next follow-up sync: %s",
            integration_id,
            next_sync_at,
        )
        return {"status": "ok", "integration_id": integration_id}


def enqueue_sync(integration_id: uuid.UUID) -> bool:
    """Sync the integration in the background now; False if it couldn't be queued."""
    return enqueue(sync_integration, str(integration_id))


@celery_app.task(name="app.worker.tasks.sync.sync_all_active_integrations")
def sync_all_active_integrations() -> dict[str, Any]:
    """
    Enqueue a sync for every syncable integration (scheduled nightly), except
    those of platforms whose app isn't set up.
    """
    available = registry.available_platforms()
    with Session(engine) as session:
        integration_ids = session.exec(
            select(Integration.id).where(
                col(Integration.status).in_(SYNCABLE_STATUSES),
                col(Integration.platform).in_(available),
            )
        ).all()

    for integration_id in integration_ids:
        enqueue(sync_integration, str(integration_id))

    logger.info("sync_all_active_integrations: enqueued %d tasks", len(integration_ids))
    return {"enqueued": len(integration_ids)}


@celery_app.task(name="app.worker.tasks.sync.sync_due_integrations")
def sync_due_integrations() -> dict[str, Any]:
    """Enqueue the follow-up syncs that are due."""
    with Session(engine) as session:
        integration_ids = [
            integration.id
            for integration in crud.claim_due_integrations(
                session=session,
                now=get_datetime_utc(),
                statuses=SYNCABLE_STATUSES,
                platforms=registry.available_platforms(),
            )
        ]

    for integration_id in integration_ids:
        enqueue(sync_integration, str(integration_id))

    if integration_ids:
        logger.info("sync_due_integrations: enqueued %d tasks", len(integration_ids))
    return {"enqueued": len(integration_ids)}
