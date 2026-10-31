from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ChannelConnection, Conversation, Customer, Message, utcnow
from app.portal.crypto import CryptoError, decrypt_secret
from app.senders.base import SendResult
from app.senders.factory import get_sender
from app.webhooks.parsers import within_service_window

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OutboundOutcome:
    message: Message
    result: SendResult


def _disclosure_text(text: str) -> str:
    if "automated" in text.lower() or "bot" in text.lower().split()[:12]:
        return text
    return f"I'm the automated assistant for {settings.brand_name}. {text}"


def send_reply(
    db: Session,
    conversation: Conversation,
    customer: Customer,
    text: str,
    *,
    bot_reply: bool = True,
    agent: str | None = None,
) -> OutboundOutcome:
    """Send one outbound turn and record it, including failures.

    WhatsApp replies outside the 24-hour service window use the approved
    template configured by WHATSAPP_TEMPLATE_NAME. Instagram's API does not
    support equivalent templates here, so an expired window fails closed and
    the dashboard can hand the thread to a human.
    """
    text = (text or "").strip()
    if not text:
        result = SendResult(False, error="empty_message")
        message = Message(
            conversation_id=conversation.id,
            direction="outbound",
            channel=conversation.channel,
            text="",
            message_type="text",
            delivery_status="failed",
            meta={"error": "empty_message"},
        )
        db.add(message)
        db.flush()
        return OutboundOutcome(message, result)

    if not customer.opted_in:
        result = SendResult(False, error="customer_not_opted_in")
        message = Message(
            conversation_id=conversation.id,
            direction="outbound",
            channel=conversation.channel,
            text=text,
            message_type="text",
            delivery_status="failed",
            meta={"error": result.error},
        )
        db.add(message)
        db.flush()
        return OutboundOutcome(message, result)

    if bot_reply:
        text = _disclosure_text(text)

    token: str | None = None
    account_id: str | None = None
    demo_connection = False
    if conversation.tenant_id:
        # Tenant traffic must never fall back to deployment-wide credentials.
        connection = db.scalar(
            select(ChannelConnection).where(
                ChannelConnection.tenant_id == conversation.tenant_id,
                ChannelConnection.channel == conversation.channel,
                ChannelConnection.status == "connected",
            )
        )
        if connection:
            try:
                token = decrypt_secret(connection.access_token_cipher)
                account_id = connection.external_account_id
                demo_connection = bool((connection.meta or {}).get("demo"))
            except CryptoError:
                logger.exception("Cannot decrypt channel token tenant=%s", conversation.tenant_id)
        if not token:
            result = SendResult(False, error="tenant_channel_not_connected")
            message = Message(
                conversation_id=conversation.id,
                direction="outbound",
                channel=conversation.channel,
                text=text,
                message_type="text",
                delivery_status="failed",
                meta={"error": result.error},
            )
            db.add(message)
            db.flush()
            return OutboundOutcome(message, result)

    sender = get_sender(
        conversation.channel,
        token=token,
        account_id=account_id,
        demo=demo_connection,
    )
    within_window = within_service_window(
        conversation.last_inbound_at,
        settings.whatsapp_window_hours
        if conversation.channel == "whatsapp"
        else settings.instagram_window_hours,
    )

    mode = "text"
    if conversation.channel == "whatsapp" and not within_window:
        # Auto-replies are in-window by construction; this path matters for
        # proactive agent messages and is deliberately template-only.
        result = sender.send_template(
            customer.external_id,
            settings.whatsapp_template_name,
            settings.whatsapp_template_language,
            [settings.brand_name],
        )
        mode = "template"
    elif conversation.channel == "instagram" and not within_window:
        result = SendResult(False, error="outside_instagram_messaging_window")
    else:
        result = sender.send_text(customer.external_id, text)

    message = Message(
        conversation_id=conversation.id,
        direction="outbound",
        channel=conversation.channel,
        text=text,
        message_type="text",
        delivery_status="sent" if result.ok else "failed",
        meta={
            "provider_message_id": result.provider_message_id,
            "attempts": result.attempts,
            "mode": mode,
            "error": result.error,
            "agent": agent,
        },
    )
    db.add(message)
    db.flush()

    if result.ok:
        conversation.last_outbound_at = utcnow()
        conversation.updated_at = utcnow()
        if bot_reply:
            conversation.bot_identified = True
    else:
        logger.error(
            "Outbound delivery failed conversation=%s channel=%s error=%s",
            conversation.id,
            conversation.channel,
            result.error,
        )
    return OutboundOutcome(message, result)
