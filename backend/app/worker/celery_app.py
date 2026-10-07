"""
Celery application: a worker runs the sync, analysis and migration tasks, and
Beat schedules the nightly sync and checks for due follow-up syncs and
analysis schedules. Task results are not stored: the tasks record their
outcome on the Integration, PerformanceAnalysis or Migration row instead.
"""

import logging
from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready

from app.core.config import settings

logger = logging.getLogger(__name__)

QUEUE_UNAVAILABLE = "The task queue is unavailable. Please try again in a moment."

celery_app = Celery(
    "prism",
    broker=settings.REDIS_URL,
    include=[
        "app.worker.tasks.sync",
        "app.worker.tasks.analysis",
        "app.worker.tasks.migration",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,
    # Acknowledge only once a task finishes, so a crashed worker's task is
    # redelivered instead of lost
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "nightly-sync-all": {
            "task": "app.worker.tasks.sync.sync_all_active_integrations",
            "schedule": crontab(hour=2, minute=0),  # UTC
        },
        # Follow-up syncs of integrations with recent posts (see
        # app.services.sync_schedule) start at most 5 minutes late
        "sync-due-integrations": {
            "task": "app.worker.tasks.sync.sync_due_integrations",
            "schedule": crontab(minute="*/5"),
        },
        # Schedules run on the hour in their own time zone; checking every
        # 5 minutes starts them at most 5 minutes late
        "start-scheduled-analyses": {
            "task": "app.worker.tasks.analysis.start_scheduled_analyses",
            "schedule": crontab(minute="*/5"),
        },
    },
)


@worker_ready.connect
def _log_platform_availability(**_kwargs: Any) -> None:
    from app.integrations.oauth import registry

    registry.log_availability()


def enqueue(task: Any, *args: Any) -> bool:
    """
    Queue a run of ``task``. Returns False, after logging why, when the broker
    can't be reached, so callers can record that the work didn't start.
    """
    try:
        task.delay(*args)
    except Exception:
        logger.exception("Could not enqueue %s%r", task.name, args)
        return False
    return True
