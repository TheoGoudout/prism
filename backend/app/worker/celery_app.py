"""
Celery application: a worker runs the sync tasks, and Beat schedules the
nightly sync. Task results are not stored: the tasks record their outcome on
the Integration row instead.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "prism", broker=settings.REDIS_URL, include=["app.worker.tasks.sync"]
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
    },
)
