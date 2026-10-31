from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete, select

from app.config import settings
from app.db import SessionLocal, init_db
from app.models import Conversation, Customer, PredictionLog, utcnow
from app.services.orchestrator import process_inbound_messages
from app.worker.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    name="app.worker.tasks.handle_inbound_batch",
    max_retries=3,
    default_retry_delay=5,
)
def handle_inbound_batch(self, messages: list[dict]) -> dict:
    init_db()
    try:
        results = process_inbound_messages(messages)
        return {
            "processed": len(results),
            "handoffs": sum(1 for result in results if result.handoff),
        }
    except Exception as exc:
        logger.exception("Inbound batch failed; retrying")
        raise self.retry(exc=exc) from exc


@celery.task(name="app.worker.tasks.purge_expired_data")
def purge_expired_data() -> dict:
    """Retention job: drop stale conversations and orphaned customer rows."""
    init_db()
    cutoff = utcnow() - timedelta(days=settings.data_retention_days)
    with SessionLocal() as db:
        stale = db.scalars(
            select(Conversation).where(
                Conversation.updated_at < cutoff,
                Conversation.status.in_(["bot", "resolved"]),
            )
        ).all()
        count = len(stale)
        for conversation in stale:
            db.delete(conversation)
        db.execute(delete(PredictionLog).where(PredictionLog.created_at < cutoff))
        db.flush()

        remaining_customers = db.scalars(select(Customer)).all()
        removed_customers = 0
        for customer in remaining_customers:
            if not customer.conversations:
                db.delete(customer)
                removed_customers += 1
        db.commit()
    logger.info(
        "Retention purge removed conversations=%d customers=%d", count, removed_customers
    )
    return {"conversations": count, "customers": removed_customers}
