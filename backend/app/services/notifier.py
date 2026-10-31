from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _handoff_text(handoff, conversation, customer_name: str | None) -> str:
    link = f"{settings.dashboard_base_url}/inbox?conversation={conversation.id}"
    who = customer_name or "a customer"
    return (
        f"🙋 Human handoff needed\n"
        f"Conversation: {conversation.id}\n"
        f"Channel: {conversation.channel}\n"
        f"Customer: {who}\n"
        f"Reason: {handoff.reason}\n"
        f"Priority: {handoff.priority}\n"
        f"Open in dashboard: {link}"
    )


def notify_handoff(handoff, conversation, customer_name: str | None = None) -> None:
    """Best-effort Slack/email notification. Never raises into the request path."""
    text = _handoff_text(handoff, conversation, customer_name)

    if settings.slack_webhook_url:
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.post(settings.slack_webhook_url, json={"text": text})
            if response.status_code >= 400:
                logger.warning("Slack handoff notification failed: HTTP %s", response.status_code)
        except httpx.HTTPError as exc:
            logger.warning("Slack handoff notification failed: %s", exc)

    if settings.smtp_host and settings.handoff_email_to:
        try:
            message = EmailMessage()
            message["Subject"] = f"[{handoff.priority.upper()}] Handoff: {conversation.channel}"
            message["From"] = settings.smtp_from or settings.smtp_username
            message["To"] = settings.handoff_email_to
            message.set_content(text)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as smtp:
                if settings.smtp_username:
                    smtp.starttls()
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        except Exception as exc:
            logger.warning("Email handoff notification failed: %s", exc)

    if not settings.slack_webhook_url and not (settings.smtp_host and settings.handoff_email_to):
        logger.info("Handoff recorded (no notifier configured): %s", text.replace("\n", " | "))
