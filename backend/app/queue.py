from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def enqueue_messages(messages: list[dict]) -> None:
    """Push normalized messages to Celery, or process inline for local dev/tests."""
    if not messages:
        return

    if settings.queue_backend == "inline" or settings.celery_task_always_eager:
        from app.services.orchestrator import process_inbound_messages

        process_inbound_messages(messages)
        return

    from app.worker.tasks import handle_inbound_batch

    handle_inbound_batch.delay(messages)


def enqueue_single(message: dict) -> None:
    enqueue_messages([message])
