from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Handoff, utcnow
from shared.labels import (
    CONVERSATION_NEEDS_HUMAN,
    HANDOFF_ASSIGNED,
    HANDOFF_OPEN,
    HANDOFF_RESOLVED,
)

logger = logging.getLogger(__name__)


def active_handoff(db: Session, conversation_id: str) -> Handoff | None:
    return db.scalar(
        select(Handoff)
        .where(
            Handoff.conversation_id == conversation_id,
            Handoff.status.in_([HANDOFF_OPEN, HANDOFF_ASSIGNED]),
        )
        .order_by(Handoff.created_at.desc())
    )


def escalate(
    db: Session,
    conversation: Conversation,
    reason: str,
    priority: str = "normal",
    note: str | None = None,
    source: str = "bot",
) -> Handoff:
    """Pause the bot and create (or reuse) the active human handoff."""
    conversation.status = CONVERSATION_NEEDS_HUMAN
    conversation.updated_at = utcnow()

    existing = active_handoff(db, conversation.id)
    if existing:
        if priority in {"high", "urgent"} and existing.priority not in {"high", "urgent"}:
            existing.priority = priority
        existing.note = note or existing.note
        db.flush()
        logger.info(
            "Handoff already active conversation=%s reason=%s", conversation.id, existing.reason
        )
        return existing

    handoff = Handoff(
        conversation_id=conversation.id,
        reason=reason[:64],
        priority=priority,
        status=HANDOFF_OPEN,
        note=note,
        source=source,
    )
    db.add(handoff)
    db.flush()
    logger.info(
        "Handoff created conversation=%s reason=%s priority=%s",
        conversation.id,
        reason,
        priority,
    )
    return handoff


def resolve_handoffs(db: Session, conversation: Conversation, note: str | None = None) -> int:
    handoffs = db.scalars(
        select(Handoff).where(
            Handoff.conversation_id == conversation.id,
            Handoff.status.in_([HANDOFF_OPEN, HANDOFF_ASSIGNED]),
        )
    ).all()
    for handoff in handoffs:
        handoff.status = HANDOFF_RESOLVED
        handoff.resolved_at = utcnow()
        if note:
            handoff.note = note
    return len(handoffs)


def assign_handoff(db: Session, handoff: Handoff, agent: str) -> Handoff:
    handoff.assigned_to = agent
    handoff.status = HANDOFF_ASSIGNED
    return handoff
