from __future__ import annotations

from app.models import Conversation, Customer, Handoff, Message
from app.schemas import (
    ConversationDetail,
    ConversationSummary,
    CustomerOut,
    HandoffOut,
    MessageOut,
)


def customer_out(customer: Customer) -> CustomerOut:
    return CustomerOut(
        id=customer.id,
        channel=customer.channel,
        external_id=customer.external_id,
        display_name=customer.display_name,
        opted_in=customer.opted_in,
        created_at=customer.created_at,
        last_seen_at=customer.last_seen_at,
    )


def message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        direction=message.direction,
        channel=message.channel,
        text=message.text,
        message_type=message.message_type,
        intent=message.intent,
        confidence=message.confidence,
        entities=message.entities or [],
        external_message_id=message.external_message_id,
        delivery_status=message.delivery_status,
        meta=message.meta or {},
        created_at=message.created_at,
    )


def handoff_out(handoff: Handoff, customer_name: str | None = None, last_message: str | None = None) -> HandoffOut:
    return HandoffOut(
        id=handoff.id,
        conversation_id=handoff.conversation_id,
        channel=handoff.conversation.channel if handoff.conversation else None,
        reason=handoff.reason,
        priority=handoff.priority,
        status=handoff.status,
        assigned_to=handoff.assigned_to,
        note=handoff.note,
        source=handoff.source,
        created_at=handoff.created_at,
        resolved_at=handoff.resolved_at,
        customer_name=customer_name,
        last_message=last_message,
    )


def conversation_summary(
    conversation: Conversation,
    *,
    last_message: Message | None = None,
    open_handoff: Handoff | None = None,
) -> ConversationSummary:
    return ConversationSummary(
        id=conversation.id,
        channel=conversation.channel,
        status=conversation.status,
        customer=customer_out(conversation.customer),
        last_intent=conversation.last_intent,
        last_confidence=conversation.last_confidence,
        assigned_agent=conversation.assigned_agent,
        bot_identified=conversation.bot_identified,
        last_message_preview=(last_message.text[:180] if last_message and last_message.text else None),
        last_message_at=last_message.created_at if last_message else None,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        open_handoff=handoff_out(open_handoff) if open_handoff else None,
    )


def conversation_detail(
    conversation: Conversation,
    messages: list[Message],
    open_handoff: Handoff | None = None,
) -> ConversationDetail:
    summary = conversation_summary(
        conversation,
        last_message=messages[-1] if messages else None,
        open_handoff=open_handoff,
    )
    return ConversationDetail(
        **summary.model_dump(),
        messages=[message_out(message) for message in messages],
    )
