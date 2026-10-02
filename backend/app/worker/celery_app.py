"""
Celery application: a worker runs the sync and analysis tasks, and Beat
schedules the nightly sync and checks for due analysis schedules. Task results
are not stored: the tasks record their outcome on the Integration or
PerformanceAnalysis row instead.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "prism",
    broker=settings.REDIS_URL,
    include=["app.worker.tasks.sync", "app.worker.tasks.analysis"],
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
        # Schedules run on the hour in their own time zone; checking every
        # 5 minutes starts them at most 5 minutes late
        "start-scheduled-analyses": {
            "task": "app.worker.tasks.analysis.start_scheduled_analyses",
            "schedule": crontab(minute="*/5"),
        },
    },
)
