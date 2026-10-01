"""
Celery application instance.

Import this module wherever a Celery app reference is needed.
Tasks are auto-discovered from app.worker.tasks.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "prism",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL.replace("/0", "/1"),  # separate DB for results
    include=[
        "app.worker.tasks.sync",
        # Platform sync modules — each registers itself via register_platform_sync
        "app.integrations.platforms.facebook",
        "app.integrations.platforms.instagram",
        "app.integrations.platforms.twitter",
        "app.integrations.platforms.linkedin",
        "app.integrations.platforms.tiktok",
        "app.integrations.platforms.google_analytics",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Retry failed tasks up to 3 times with exponential backoff
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Beat schedule — nightly sync at 02:00 UTC
    beat_schedule={
        "nightly-sync-all": {
            "task": "app.worker.tasks.sync.sync_all_active_integrations",
            "schedule": crontab(hour=2, minute=0),
        },
    },
)
