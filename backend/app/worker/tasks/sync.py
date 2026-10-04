"""
Sync tasks — fetch fresh metrics from the connected platforms.

`sync_integration` syncs one integration and records the outcome on it
(active / error / expired). `sync_all_active_integrations` runs nightly and
enqueues one `sync_integration` per integration.
"""

import logging
import uuid
from typing import Any

import httpx
from sqlmodel import Session, col, select

from app import crud
from app.core.db import engine
from app.integrations.oauth import registry
from app.integrations.platforms import SYNC_FUNCTIONS
from app.integrations.tokens import TokenExpiredError, ensure_fresh_token
from app.models.integration import Integration, IntegrationStatus
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# Statuses picked up by the scheduled sync. `error` is included so a transient
# failure doesn't stop an integration from syncing for good; `expired` and
# `disconnected` integrations need the user to reconnect first.
SYNCABLE_STATUSES = (IntegrationStatus.active, IntegrationStatus.error)

RECONNECT_MESSAGE = "The platform rejected our access token. Please reconnect."


def _is_auth_error(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401


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
            ensure_fresh_token(session=session, integration=integration)
            access_token = crud.get_access_token(integration)
            if not access_token:
                raise TokenExpiredError("No access token stored. Please reconnect.")
            SYNC_FUNCTIONS[integration.platform](session, integration, access_token)
        except TokenExpiredError as exc:
            crud.mark_integration_expired(
                session=session, integration=integration, error=str(exc)
            )
            return {"status": "expired", "integration_id": integration_id}
        except Exception as exc:
            if _is_auth_error(exc):  # token revoked: retrying won't help
                crud.mark_integration_expired(
                    session=session, integration=integration, error=RECONNECT_MESSAGE
                )
                return {"status": "expired", "integration_id": integration_id}
            logger.exception("sync_integration: error for %s", integration_id)
            crud.mark_integration_error(
                session=session, integration=integration, error=str(exc)
            )
            raise self.retry(exc=exc)

        crud.mark_integration_synced(session=session, integration=integration)
        logger.info("sync_integration: OK for %s", integration_id)
        return {"status": "ok", "integration_id": integration_id}


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
        sync_integration.delay(str(integration_id))

    logger.info("sync_all_active_integrations: enqueued %d tasks", len(integration_ids))
    return {"enqueued": len(integration_ids)}
