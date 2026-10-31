from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import settings

SUPPORTED_CHANNELS = {"whatsapp", "instagram"}


def _utc_from_seconds(value: Any) -> datetime:
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return datetime.utcnow()
    return datetime.fromtimestamp(seconds, tz=UTC).replace(tzinfo=None)


def _utc_from_milliseconds(value: Any) -> datetime:
    try:
        millis = int(float(value))
    except (TypeError, ValueError):
        return datetime.utcnow()
    return datetime.fromtimestamp(millis / 1000, tz=UTC).replace(tzinfo=None)


def _synthetic_id(channel: str, sender: str, timestamp: str, text: str) -> str:
    digest = hashlib.sha1(f"{channel}:{sender}:{timestamp}:{text}".encode()).hexdigest()[:24]
    return f"{channel}_{digest}"


@dataclass(slots=True)
class NormalizedMessage:
    channel: str
    sender_id: str
    recipient_id: str
    text: str
    timestamp: datetime
    message_type: str = "text"
    external_message_id: str = ""
    customer_name: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "text": self.text,
            "timestamp": self.timestamp.isoformat(),
            "message_type": self.message_type,
            "external_message_id": self.external_message_id,
            "customer_name": self.customer_name,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> NormalizedMessage:
        raw_ts = payload.get("timestamp")
        if isinstance(raw_ts, datetime):
            timestamp = raw_ts.replace(tzinfo=None)
        else:
            try:
                timestamp = datetime.fromisoformat(str(raw_ts)).replace(tzinfo=None)
            except (TypeError, ValueError):
                timestamp = datetime.utcnow()
        return cls(
            channel=payload["channel"],
            sender_id=str(payload["sender_id"]),
            recipient_id=str(payload.get("recipient_id", "")),
            text=payload.get("text") or "",
            timestamp=timestamp,
            message_type=payload.get("message_type") or "text",
            external_message_id=payload.get("external_message_id") or "",
            customer_name=payload.get("customer_name"),
            metadata=payload.get("metadata") or {},
        )


def parse_whatsapp(payload: dict) -> list[NormalizedMessage]:
    """Normalize WhatsApp Cloud API message webhooks.

    Status callbacks, unknown event types, and malformed entries are skipped
    rather than raising, because Meta retries the whole batch on any 5xx.
    """
    messages: list[NormalizedMessage] = []
    default_recipient = settings.phone_number_id

    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            recipient_id = str(metadata.get("phone_number_id") or default_recipient or "")
            contact_names = {
                str(contact.get("wa_id")): (contact.get("profile") or {}).get("name")
                for contact in value.get("contacts") or []
                if isinstance(contact, dict)
            }

            for item in value.get("messages") or []:
                if not isinstance(item, dict):
                    continue
                sender_id = str(item.get("from") or "")
                if not sender_id:
                    continue

                raw_type = str(item.get("type") or "unsupported")
                text = ""
                meta: dict = {
                    "raw_type": raw_type,
                    "phone_number_id": recipient_id,
                    "display_phone_number": metadata.get("display_phone_number"),
                }

                if raw_type == "text":
                    text = ((item.get("text") or {}).get("body") or "").strip()
                    message_type = "text"
                elif raw_type == "button":
                    text = ((item.get("button") or {}).get("text") or "").strip()
                    message_type = "button"
                elif raw_type == "interactive":
                    interactive = item.get("interactive") or {}
                    reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
                    text = (reply.get("title") or "").strip()
                    meta["interactive_id"] = reply.get("id")
                    message_type = "interactive"
                elif raw_type == "reaction":
                    meta["emoji"] = (item.get("reaction") or {}).get("emoji")
                    message_type = "reaction"
                elif raw_type in {"image", "video", "document", "audio", "sticker"}:
                    media = item.get(raw_type) or {}
                    text = (media.get("caption") or "").strip()
                    meta["media_id"] = media.get("id")
                    meta["mime_type"] = media.get("mime_type")
                    message_type = raw_type
                elif raw_type == "location":
                    location = item.get("location") or {}
                    meta["latitude"] = location.get("latitude")
                    meta["longitude"] = location.get("longitude")
                    message_type = "location"
                else:
                    message_type = raw_type if raw_type else "unsupported"

                timestamp = _utc_from_seconds(item.get("timestamp"))
                external_id = str(item.get("id") or "")
                if not external_id:
                    external_id = _synthetic_id(
                        "whatsapp", sender_id, str(item.get("timestamp")), text
                    )

                context = item.get("context") or {}
                if context.get("id"):
                    meta["reply_to_message_id"] = context.get("id")

                messages.append(
                    NormalizedMessage(
                        channel="whatsapp",
                        sender_id=sender_id,
                        recipient_id=recipient_id,
                        text=text,
                        timestamp=timestamp,
                        message_type=message_type,
                        external_message_id=external_id,
                        customer_name=contact_names.get(sender_id),
                        metadata=meta,
                    )
                )

    return messages


def parse_instagram(payload: dict) -> list[NormalizedMessage]:
    """Normalize Instagram Messaging webhooks, ignoring echoes and receipts."""
    messages: list[NormalizedMessage] = []
    default_recipient = settings.ig_business_account_id

    for entry in payload.get("entry") or []:
        account_id = str(entry.get("id") or default_recipient or "")
        for event in entry.get("messaging") or []:
            if not isinstance(event, dict):
                continue
            message = event.get("message")
            if not message or message.get("is_echo"):
                continue
            # Read receipts and delivery events have no message body; skip them.
            if event.get("read") or event.get("delivery"):
                continue

            sender_id = str((event.get("sender") or {}).get("id") or "")
            recipient_id = str((event.get("recipient") or {}).get("id") or account_id)
            if not sender_id or sender_id == recipient_id:
                continue

            raw_ts = event.get("timestamp")
            text = ""
            meta: dict = {"raw_type": "message"}
            message_type = "text"

            if message.get("text"):
                text = str(message["text"]).strip()
            elif message.get("attachments"):
                attachment = (message.get("attachments") or [{}])[0] or {}
                attachment_type = str(attachment.get("type") or "file")
                message_type = attachment_type
                meta["attachment_url"] = attachment.get("payload", {}).get("url")
                if message.get("text"):
                    text = str(message["text"]).strip()
            elif message.get("quick_reply"):
                text = str((message.get("quick_reply") or {}).get("payload") or "").strip()
                message_type = "quick_reply"

            postback = event.get("postback") or {}
            if not text and postback:
                text = str(postback.get("title") or postback.get("payload") or "").strip()
                message_type = "postback"
                meta["raw_type"] = "postback"
            reaction = event.get("reaction") or {}
            if reaction:
                text = ""
                message_type = "reaction"
                meta["emoji"] = reaction.get("emoji")

            # An empty text event (e.g. unsupported attachment with no text).
            if (
                not text
                and message_type in {"text", "quick_reply", "postback", "reaction"}
                and not message.get("attachments")
            ):
                continue

            external_id = str(message.get("mid") or "")
            if not external_id:
                external_id = _synthetic_id("instagram", sender_id, str(raw_ts), text)

            messages.append(
                NormalizedMessage(
                    channel="instagram",
                    sender_id=sender_id,
                    recipient_id=recipient_id,
                    text=text,
                    timestamp=_utc_from_milliseconds(raw_ts),
                    message_type=message_type,
                    external_message_id=external_id,
                    customer_name=None,
                    metadata=meta,
                )
            )

    return messages


def parse_webhook(channel: str, payload: dict) -> list[NormalizedMessage]:
    if channel == "whatsapp":
        return parse_whatsapp(payload)
    if channel == "instagram":
        return parse_instagram(payload)
    raise ValueError(f"Unsupported channel: {channel}")


def payload_fingerprint(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:32]


def within_service_window(last_inbound_at: datetime | None, hours: int) -> bool:
    if not last_inbound_at:
        return False
    return datetime.utcnow() - last_inbound_at <= timedelta(hours=hours)
