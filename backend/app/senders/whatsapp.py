from __future__ import annotations

import logging

from app.config import settings
from app.senders.base import BaseSender, SendResult, chunk_text, post_with_retry

logger = logging.getLogger(__name__)


class WhatsAppSender(BaseSender):
    channel = "whatsapp"

    def __init__(self, token: str | None = None, phone_number_id: str | None = None) -> None:
        self.token = token or settings.whatsapp_token
        self.phone_number_id = phone_number_id or settings.phone_number_id
        self.base_url = settings.graph_base_url.rstrip("/")
        self.version = settings.whatsapp_api_version
        self.timeout = settings.sender_timeout_seconds
        self.max_attempts = settings.sender_max_retries

    @property
    def url(self) -> str:
        return f"{self.base_url}/{self.version}/{self.phone_number_id}/messages"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _send_payload(self, payload: dict) -> SendResult:
        status_code, body, error, attempts = post_with_retry(
            self.url,
            payload,
            self.headers,
            timeout=self.timeout,
            max_attempts=self.max_attempts,
        )
        if error:
            logger.error("WhatsApp send failed attempts=%d error=%s", attempts, error)
            return SendResult(False, status_code=status_code, error=error, attempts=attempts)
        messages = body.get("messages") or []
        provider_id = messages[0].get("id") if messages else None
        return SendResult(True, provider_message_id=provider_id, status_code=status_code, attempts=attempts)

    def send_text(self, recipient_id: str, text: str) -> SendResult:
        result: SendResult | None = None
        for part in chunk_text(text):
            result = self._send_payload(
                {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient_id,
                    "type": "text",
                    "text": {"preview_url": False, "body": part},
                }
            )
            if not result.ok:
                return result
        return result or SendResult(False, error="empty_message")

    def send_template(
        self,
        recipient_id: str,
        template_name: str,
        language: str,
        parameters: list[str] | None = None,
    ) -> SendResult:
        components = []
        if parameters:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(value)} for value in parameters],
                }
            )
        return self._send_payload(
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_id,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language},
                    "components": components,
                },
            }
        )
