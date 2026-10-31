from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.serializers import (
    conversation_detail,
    conversation_summary,
    handoff_out,
    message_out,
)
from app.db import get_db
from app.dialogue.session import session_store
from app.models import Conversation, Customer, Message, utcnow
from app.portal.service import notify_assignment
from app.schemas import (
    AssignIn,
    ConversationDetail,
    ConversationSummary,
    HandoffIn,
    HandoffOut,
    MessageOut,
    ReplyIn,
    ResolveIn,
)
from app.security import require_admin
from app.services.handoff import (
    active_handoff,
    assign_handoff,
    escalate,
    resolve_handoffs,
)
from app.services.notifier import notify_handoff
from app.services.outbound import send_reply
from shared.labels import CONVERSATION_RESOLVED

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/conversations",
    tags=["conversations"],
    dependencies=[Depends(require_admin)],
)


def _get_conversation(db: Session, conversation_id: str) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .options(joinedload(Conversation.customer))
        .where(Conversation.id == conversation_id)
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _last_message(db: Session, conversation_id: str) -> Message | None:
    return db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )


@router.get("", response_model=list[ConversationSummary])
def list_conversations(
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    channel: str | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> list[ConversationSummary]:
    query = (
        select(Conversation)
        .options(joinedload(Conversation.customer))
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter:
        query = query.where(Conversation.status == status_filter)
    if channel:
        query = query.where(Conversation.channel == channel)
    if q:
        query = query.join(Customer).where(
            or_(
                Customer.display_name.ilike(f"%{q}%"),
                Customer.external_id.ilike(f"%{q}%"),
                Conversation.id.ilike(f"%{q}%"),
            )
        )

    conversations = db.scalars(query).all()
    output: list[ConversationSummary] = []
    for conversation in conversations:
        last = _last_message(db, conversation.id)
        handoff = active_handoff(db, conversation.id)
        output.append(conversation_summary(conversation, last_message=last, open_handoff=handoff))
    return output


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> ConversationDetail:
    conversation = db.scalar(
        select(Conversation)
        .options(
            joinedload(Conversation.customer),
            selectinload(Conversation.messages),
        )
        .where(Conversation.id == conversation_id)
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = list(conversation.messages)
    return conversation_detail(conversation, messages, active_handoff(db, conversation.id))


@router.post("/{conversation_id}/reply", response_model=MessageOut)
def agent_reply(
    conversation_id: str,
    body: ReplyIn,
    db: Session = Depends(get_db),
) -> MessageOut:
    conversation = _get_conversation(db, conversation_id)
    agent = body.agent or "dashboard"
    if not conversation.assigned_agent:
        conversation.assigned_agent = agent
    outcome = send_reply(
        db,
        conversation,
        conversation.customer,
        body.text,
        bot_reply=False,
        agent=agent,
    )
    if not outcome.result.ok:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Channel delivery failed: {outcome.result.error}",
        )
    db.commit()
    return message_out(outcome.message)


@router.post("/{conversation_id}/handoff", response_model=HandoffOut)
def manual_handoff(
    conversation_id: str,
    body: HandoffIn,
    db: Session = Depends(get_db),
) -> HandoffOut:
    conversation = _get_conversation(db, conversation_id)
    handoff = escalate(
        db,
        conversation,
        body.reason,
        priority=body.priority,
        note=body.note,
        source="agent",
    )
    if body.agent:
        conversation.assigned_agent = body.agent
        assign_handoff(db, handoff, body.agent)
    db.commit()
    notify_handoff(handoff, conversation, conversation.customer.display_name)
    return handoff_out(handoff, conversation.customer.display_name)


@router.post("/{conversation_id}/assign", response_model=ConversationSummary)
def assign_conversation(
    conversation_id: str,
    body: AssignIn,
    db: Session = Depends(get_db),
) -> ConversationSummary:
    conversation = _get_conversation(db, conversation_id)
    conversation.assigned_agent = body.agent
    handoff = active_handoff(db, conversation.id)
    if handoff:
        assign_handoff(db, handoff, body.agent)
    db.commit()
    try:
        notify_assignment(db, conversation, body.agent)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Assignment notification failed conversation=%s", conversation.id)
    return conversation_summary(
        conversation, last_message=_last_message(db, conversation.id), open_handoff=handoff
    )


@router.post("/{conversation_id}/resolve", response_model=ConversationSummary)
def resolve_conversation(
    conversation_id: str,
    body: ResolveIn,
    db: Session = Depends(get_db),
) -> ConversationSummary:
    conversation = _get_conversation(db, conversation_id)
    conversation.status = CONVERSATION_RESOLVED
    conversation.updated_at = utcnow()
    if body.agent:
        conversation.assigned_agent = body.agent
    resolve_handoffs(db, conversation, note=body.note)
    session_store.delete(conversation.id)
    db.commit()
    return conversation_summary(conversation, last_message=_last_message(db, conversation.id))


@router.post("/{conversation_id}/reopen", response_model=ConversationSummary)
def reopen_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> ConversationSummary:
    conversation = _get_conversation(db, conversation_id)
    conversation.status = "bot"
    conversation.updated_at = utcnow()
    resolve_handoffs(db, conversation, note="Reopened for automated handling")
    db.commit()
    return conversation_summary(conversation, last_message=_last_message(db, conversation.id))
