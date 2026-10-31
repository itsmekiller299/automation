from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.serializers import handoff_out
from app.db import get_db
from app.models import Conversation, Handoff, Message, utcnow
from app.schemas import AssignIn, HandoffOut, ResolveIn
from app.security import require_admin
from app.services.handoff import assign_handoff, resolve_handoffs
from shared.labels import CONVERSATION_RESOLVED, HANDOFF_ASSIGNED, HANDOFF_OPEN, HANDOFF_RESOLVED

router = APIRouter(
    prefix="/api/handoffs",
    tags=["handoffs"],
    dependencies=[Depends(require_admin)],
)


def _last_message(db: Session, conversation_id: str) -> str | None:
    message = db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return message.text if message else None


@router.get("", response_model=list[HandoffOut])
def list_handoffs(
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    priority: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    db: Session = Depends(get_db),
) -> list[HandoffOut]:
    query = (
        select(Handoff)
        .options(joinedload(Handoff.conversation).joinedload(Conversation.customer))
        .order_by(Handoff.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        query = query.where(Handoff.status == status_filter)
    else:
        query = query.where(Handoff.status.in_([HANDOFF_OPEN, HANDOFF_ASSIGNED]))
    if priority:
        query = query.where(Handoff.priority == priority)

    handoffs = db.scalars(query).all()
    return [
        handoff_out(
            handoff,
            handoff.conversation.customer.display_name,
            _last_message(db, handoff.conversation_id),
        )
        for handoff in handoffs
    ]


def _get_handoff(db: Session, handoff_id: str) -> Handoff:
    handoff = db.scalar(
        select(Handoff)
        .options(joinedload(Handoff.conversation).joinedload(Conversation.customer))
        .where(Handoff.id == handoff_id)
    )
    if not handoff:
        raise HTTPException(status_code=404, detail="Handoff not found")
    return handoff


@router.post("/{handoff_id}/assign", response_model=HandoffOut)
def assign(
    handoff_id: str, body: AssignIn, db: Session = Depends(get_db)
) -> HandoffOut:
    handoff = _get_handoff(db, handoff_id)
    assign_handoff(db, handoff, body.agent)
    handoff.conversation.assigned_agent = body.agent
    db.commit()
    return handoff_out(
        handoff,
        handoff.conversation.customer.display_name,
        _last_message(db, handoff.conversation_id),
    )


@router.post("/{handoff_id}/resolve", response_model=HandoffOut)
def resolve(
    handoff_id: str, body: ResolveIn, db: Session = Depends(get_db)
) -> HandoffOut:
    handoff = _get_handoff(db, handoff_id)
    handoff.status = HANDOFF_RESOLVED
    handoff.resolved_at = utcnow()
    if body.note:
        handoff.note = body.note
    if body.agent:
        handoff.assigned_to = body.agent
        handoff.conversation.assigned_agent = body.agent
    handoff.conversation.status = CONVERSATION_RESOLVED
    handoff.conversation.updated_at = utcnow()
    resolve_handoffs(db, handoff.conversation, note=body.note)
    db.commit()
    return handoff_out(
        handoff,
        handoff.conversation.customer.display_name,
        _last_message(db, handoff.conversation_id),
    )
