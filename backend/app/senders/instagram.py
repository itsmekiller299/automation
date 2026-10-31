from __future__ import annotations

import logging

from app.config import settings
from app.senders.base import BaseSender, SendResult, chunk_text, post_with_retry

logger = logging.getLogger(__name__)


class InstagramSender(BaseSender):
    channel = "instagram"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or settings.ig_page_token
        self.base_url = settings.graph_base_url.rstrip("/")
        self.version = settings.ig_api_version
        self.timeout = settings.sender_timeout_seconds
        self.max_attempts = settings.sender_max_retries

    @property
    def url(self) -> str:
        return f"{self.base_url}/{self.version}/me/messages"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def send_text(self, recipient_id: str, text: str) -> SendResult:
        result: SendResult | None = None
        for part in chunk_text(text, limit=900):
            status_code, body, error, attempts = post_with_retry(
                self.url,
                {
                    "recipient": {"id": recipient_id},
                    "messaging_type": "RESPONSE",
                    "message": {"text": part},
                },
                self.headers,
                timeout=self.timeout,
                max_attempts=self.max_attempts,
            )
            if error:
                logger.error("Instagram send failed attempts=%d error=%s", attempts, error)
                return SendResult(False, status_code=status_code, error=error, attempts=attempts)
            provider_id = body.get("message_id")
            result = SendResult(
                True, provider_message_id=provider_id, status_code=status_code, attempts=attempts
            )
        return result or SendResult(False, error="empty_message")

    def send_template(
        self,
        recipient_id: str,
        template_name: str,
        language: str,
        parameters: list[str] | None = None,
    ) -> SendResult:
        # Instagram does not use WhatsApp-style templates. Outside the messaging
        # window a human must use an approved tag/flow in Meta's inbox.
        return SendResult(False, error="instagram_templates_not_supported")
