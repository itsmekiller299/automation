from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.dialogue.manager import Decision, DialogueManager
from app.dialogue.session import SessionState, session_store
from app.models import (
    Conversation,
    Customer,
    Message,
    PredictionLog,
    Tenant,
    utcnow,
)
from app.nlu.pipeline import get_nlu
from app.portal.service import resolve_tenant_for_account
from app.services.handoff import escalate, resolve_handoffs
from app.services.notifier import notify_handoff
from app.services.outbound import send_reply
from app.webhooks.parsers import NormalizedMessage
from shared.labels import CONVERSATION_NEEDS_HUMAN, CONVERSATION_RESOLVED

logger = logging.getLogger(__name__)

_manager: DialogueManager | None = None


def get_dialogue_manager() -> DialogueManager:
    global _manager
    if _manager is None:
        _manager = DialogueManager()
    return _manager


@dataclass(slots=True)
class ProcessResult:
    conversation_id: str
    inbound_message_id: str
    intent: str
    confidence: float
    handoff: bool
    reply: str | None
    deduplicated: bool = False


def process_inbound_messages(payloads: list[dict]) -> list[ProcessResult]:
    results: list[ProcessResult] = []
    for payload in payloads:
        try:
            message = NormalizedMessage.from_dict(payload)
            result = process_inbound_message(message)
            if result:
                results.append(result)
        except Exception:
            # A poison message must not stop the rest of the batch. The inbound
            # row and error are visible in logs; in production ship this to a DLQ.
            logger.exception(
                "Failed to process inbound message %s", payload.get("external_message_id")
            )
    return results


def _find_customer(db, message: NormalizedMessage, tenant_id: str | None = None) -> Customer:
    customer = db.scalar(
        select(Customer).where(
            Customer.channel == message.channel,
            Customer.external_id == message.sender_id,
        )
    )
    if customer:
        if tenant_id and not customer.tenant_id:
            customer.tenant_id = tenant_id
        if message.customer_name and message.customer_name != customer.display_name:
            customer.display_name = message.customer_name
        customer.last_seen_at = utcnow()
        customer.opted_in = True
        return customer

    customer = Customer(
        tenant_id=tenant_id,
        channel=message.channel,
        external_id=message.sender_id,
        display_name=message.customer_name,
        opted_in=True,
        last_seen_at=utcnow(),
    )
    db.add(customer)
    db.flush()
    return customer


def _find_conversation(db, customer: Customer, tenant_id: str | None = None) -> Conversation:
    tenant_filter = (
        Conversation.tenant_id.is_(None)
        if tenant_id is None
        else Conversation.tenant_id == tenant_id
    )
    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.customer_id == customer.id,
            tenant_filter,
            Conversation.status.in_(["bot", CONVERSATION_NEEDS_HUMAN]),
        )
        .order_by(Conversation.updated_at.desc())
    )
    if conversation:
        return conversation
    conversation = Conversation(
        tenant_id=tenant_id,
        customer_id=customer.id,
        channel=customer.channel,
        status="bot",
    )
    db.add(conversation)
    db.flush()
    return conversation


def process_inbound_message(message: NormalizedMessage) -> ProcessResult | None:
    db = SessionLocal()
    handoff = None
    customer: Customer | None = None
    conversation: Conversation | None = None
    state: SessionState | None = None
    try:
        if message.external_message_id:
            existing = db.scalar(
                select(Message).where(Message.external_message_id == message.external_message_id)
            )
            if existing:
                logger.info(
                    "Duplicate inbound message ignored conversation=%s", existing.conversation_id
                )
                return ProcessResult(
                    conversation_id=existing.conversation_id,
                    inbound_message_id=existing.id,
                    intent=existing.intent or "other",
                    confidence=existing.confidence or 0.0,
                    handoff=False,
                    reply=None,
                    deduplicated=True,
                )

        tenant_id = resolve_tenant_for_account(db, message.channel, message.recipient_id)
        customer = _find_customer(db, message, tenant_id=tenant_id)
        conversation = _find_conversation(db, customer, tenant_id=tenant_id)
        conversation.last_inbound_at = message.timestamp
        conversation.updated_at = utcnow()

        inbound = Message(
            conversation_id=conversation.id,
            direction="inbound",
            channel=message.channel,
            text=message.text,
            message_type=message.message_type,
            external_message_id=message.external_message_id or None,
            delivery_status="received",
            meta=message.metadata,
            created_at=message.timestamp,
        )
        db.add(inbound)
        db.flush()

        if conversation.tenant_id:
            tenant = db.get(Tenant, conversation.tenant_id)
            if tenant and not tenant.automation_enabled:
                db.commit()
                logger.info(
                    "Automation inactive; inbound stored without reply tenant=%s conversation=%s",
                    tenant.id,
                    conversation.id,
                )
                return ProcessResult(
                    conversation_id=conversation.id,
                    inbound_message_id=inbound.id,
                    intent="other",
                    confidence=0.0,
                    handoff=False,
                    reply=None,
                )

        nlu = get_nlu().predict(message.text)
        decision: Decision | None = None
        state = session_store.get(conversation.id)
        state.bot_identified = conversation.bot_identified

        if conversation.status == CONVERSATION_NEEDS_HUMAN:
            # Bot is paused for this thread. Still classify and log the message
            # so agents see intent/confidence in the dashboard.
            inbound.intent = nlu.intent
            inbound.confidence = nlu.confidence
            inbound.entities = nlu.entities
            db.add(
                PredictionLog(
                    conversation_id=conversation.id,
                    message_id=inbound.id,
                    intent=nlu.intent,
                    confidence=nlu.confidence,
                    model_version=nlu.model_version,
                    top_intents=nlu.top_intents,
                    entities=nlu.entities,
                )
            )
            conversation.last_intent = nlu.intent
            conversation.last_confidence = nlu.confidence
            db.commit()
            logger.info("Bot paused; message logged for human conversation=%s", conversation.id)
            return ProcessResult(
                conversation_id=conversation.id,
                inbound_message_id=inbound.id,
                intent=nlu.intent,
                confidence=nlu.confidence,
                handoff=False,
                reply=None,
            )

        try:
            decision = get_dialogue_manager().handle(
                message,
                conversation,
                state,
                nlu,
                db=db,
                customer_name=customer.display_name,
            )
        except Exception:
            logger.exception("Dialogue pipeline failed conversation=%s", conversation.id)
            decision = Decision(
                reply=(
                    "I hit a technical issue while handling that. I've asked a human teammate "
                    "to step in so nothing gets missed."
                ),
                intent=nlu.intent,
                confidence=nlu.confidence,
                entities=nlu.entities,
                top_intents=nlu.top_intents,
                handoff=True,
                handoff_reason="pipeline_error",
                priority="high",
                model_version=nlu.model_version,
                source=nlu.source,
            )

        inbound.intent = decision.intent
        inbound.confidence = decision.confidence
        inbound.entities = decision.entities
        inbound.meta = {
            **(message.metadata or {}),
            "model_version": decision.model_version,
            "source": decision.source,
            "top_intents": decision.top_intents,
        }
        conversation.last_intent = decision.intent
        conversation.last_confidence = decision.confidence
        conversation.updated_at = utcnow()
        db.add(
            PredictionLog(
                conversation_id=conversation.id,
                message_id=inbound.id,
                intent=decision.intent,
                confidence=decision.confidence,
                model_version=decision.model_version,
                top_intents=decision.top_intents,
                entities=decision.entities,
            )
        )

        delivery_failed = False
        if decision.reply:
            outcome = send_reply(
                db,
                conversation,
                customer,
                decision.reply,
                bot_reply=True,
            )
            delivery_failed = not outcome.result.ok
            if outcome.result.ok:
                state.bot_identified = True

        if decision.handoff:
            handoff = escalate(
                db,
                conversation,
                decision.handoff_reason or "unknown",
                priority=decision.priority,
                source="bot",
            )
        elif delivery_failed:
            handoff = escalate(
                db,
                conversation,
                "delivery_failed",
                priority="high",
                note="Automated reply could not be delivered.",
                source="bot",
            )

        if decision.resolved:
            conversation.status = CONVERSATION_RESOLVED
            resolve_handoffs(db, conversation)
            conversation.updated_at = utcnow()

        db.commit()
        session_store.save(conversation.id, state)
        logger.info(
            "Processed inbound channel=%s conversation=%s intent=%s confidence=%.3f handoff=%s",
            message.channel,
            conversation.id,
            decision.intent,
            decision.confidence,
            decision.handoff,
        )
        return ProcessResult(
            conversation_id=conversation.id,
            inbound_message_id=inbound.id,
            intent=decision.intent,
            confidence=decision.confidence,
            handoff=decision.handoff,
            reply=decision.reply,
        )
    except IntegrityError:
        db.rollback()
        logger.info("Duplicate/racing inbound message ignored: %s", message.external_message_id)
        return None
    except Exception:
        db.rollback()
        logger.exception(
            "Unhandled inbound processing failure conversation=%s",
            getattr(conversation, "id", None),
        )
        raise
    finally:
        db.close()
        if handoff is not None and conversation is not None:
            # The handoff is committed before this best-effort notification.
            notify_handoff(
                handoff,
                conversation,
                customer.display_name if customer else None,
            )
