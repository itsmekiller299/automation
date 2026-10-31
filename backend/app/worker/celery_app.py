from __future__ import annotations

from celery import Celery

from app.config import settings

celery = Celery(
    "autoreply",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    task_time_limit=120,
    task_soft_time_limit=90,
    beat_schedule={
        "purge-expired-conversations": {
            "task": "app.worker.tasks.purge_expired_data",
            "schedule": 86_400.0,
        }
    },
)
