"""
Sync tasks — fetch fresh metrics from every connected platform.

Platform-specific sync functions are registered via `register_platform_sync`
(each module in app.integrations.platforms calls it once on import), so this
task dispatcher never needs to know about individual platforms.
"""

import logging
import uuid
from collections.abc import Callable
from typing import Any

import httpx
from sqlmodel import Session, col, select

from app.core.db import engine
from app.models.integration import Integration, IntegrationStatus
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform sync registry
# ---------------------------------------------------------------------------

# Maps Platform → sync function signature: (session, integration) -> None
_platform_sync: dict[str, Callable[..., None]] = {}

# Statuses that are picked up by scheduled syncs. `error` is included so a
# transient failure doesn't permanently stop an integration from syncing;
# `expired` and `disconnected` need the user to reconnect first.
SYNCABLE_STATUSES = (IntegrationStatus.active, IntegrationStatus.error)


def register_platform_sync(platform_value: str, fn: Callable[..., None]) -> None:
    """Register a sync function for a platform."""
    _platform_sync[platform_value] = fn


def _is_auth_error(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="app.worker.tasks.sync.sync_integration",
)
def sync_integration(self: Any, integration_id: str) -> dict[str, Any]:
    """
    Sync a single integration.
    Refreshes the access token first if it is about to expire.
    Retries up to 3 times on transient errors (network timeouts, rate limits).
    """
    from app import crud
    from app.integrations.tokens import TokenExpiredError, ensure_fresh_token

    iid = uuid.UUID(integration_id)

    with Session(engine) as session:
        integration = crud.get_integration(session=session, integration_id=iid)
        if not integration:
            logger.warning("sync_integration: integration %s not found", integration_id)
            return {"status": "not_found", "integration_id": integration_id}

        if integration.status in (
            IntegrationStatus.disconnected,
            IntegrationStatus.expired,
        ):
            return {"status": "skipped", "reason": integration.status.value}

        sync_fn = _platform_sync.get(integration.platform.value)
        if sync_fn is None:
            logger.info(
                "sync_integration: no sync registered for platform %s",
                integration.platform,
            )
            return {
                "status": "skipped",
                "reason": f"no sync for {integration.platform}",
            }

        try:
            ensure_fresh_token(session=session, integration=integration)
            sync_fn(session=session, integration=integration)
            crud.mark_integration_synced(session=session, integration=integration)
            logger.info("sync_integration: OK for %s", integration_id)
            return {"status": "ok", "integration_id": integration_id}

        except TokenExpiredError as exc:
            crud.mark_integration_expired(
                session=session, integration=integration, error=str(exc)
            )
            return {"status": "expired", "integration_id": integration_id}

        except Exception as exc:
            if _is_auth_error(exc):
                # Token revoked on the provider side — retrying won't help
                crud.mark_integration_expired(
                    session=session,
                    integration=integration,
                    error="The platform rejected our access token. Please reconnect.",
                )
                return {"status": "expired", "integration_id": integration_id}
            logger.error(
                "sync_integration: error for %s: %s", integration_id, exc, exc_info=True
            )
            crud.mark_integration_error(
                session=session, integration=integration, error=str(exc)
            )
            raise self.retry(exc=exc)


@celery_app.task(name="app.worker.tasks.sync.sync_all_active_integrations")
def sync_all_active_integrations() -> dict[str, Any]:
    """
    Enqueue a sync_integration task for every syncable integration.
    Scheduled nightly by Celery Beat.
    """
    with Session(engine) as session:
        integrations = session.exec(
            select(Integration).where(col(Integration.status).in_(SYNCABLE_STATUSES))
        ).all()

    count = len(integrations)
    for integ in integrations:
        sync_integration.delay(str(integ.id))

    logger.info("sync_all_active_integrations: enqueued %d tasks", count)
    return {"enqueued": count}


@celery_app.task(name="app.worker.tasks.sync.sync_workspace_integrations")
def sync_workspace_integrations(workspace_id: str) -> dict[str, Any]:
    """Enqueue sync tasks for all syncable integrations in a specific workspace."""
    wid = uuid.UUID(workspace_id)
    with Session(engine) as session:
        integrations = session.exec(
            select(Integration).where(
                Integration.workspace_id == wid,
                col(Integration.status).in_(SYNCABLE_STATUSES),
            )
        ).all()

    count = len(integrations)
    for integ in integrations:
        sync_integration.delay(str(integ.id))

    return {"workspace_id": workspace_id, "enqueued": count}
