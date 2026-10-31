from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SendResult:
    ok: bool
    provider_message_id: str | None = None
    status_code: int | None = None
    error: str | None = None
    attempts: int = 1


class BaseSender(ABC):
    channel = "base"

    @abstractmethod
    def send_text(self, recipient_id: str, text: str) -> SendResult:
        raise NotImplementedError

    @abstractmethod
    def send_template(
        self,
        recipient_id: str,
        template_name: str,
        language: str,
        parameters: list[str] | None = None,
    ) -> SendResult:
        raise NotImplementedError


class MockSender(BaseSender):
    """Local/mock sender. Never contacts Meta."""

    def __init__(self, channel: str) -> None:
        self.channel = channel
        self.sent: list[dict] = []

    def send_text(self, recipient_id: str, text: str) -> SendResult:
        message_id = f"mock_{self.channel}_{len(self.sent) + 1}"
        self.sent.append({"to": recipient_id, "text": text, "type": "text"})
        logger.info("[mock:%s] to=%s text=%r", self.channel, recipient_id, text[:160])
        return SendResult(ok=True, provider_message_id=message_id, status_code=200)

    def send_template(
        self,
        recipient_id: str,
        template_name: str,
        language: str,
        parameters: list[str] | None = None,
    ) -> SendResult:
        message_id = f"mock_{self.channel}_{len(self.sent) + 1}"
        self.sent.append(
            {
                "to": recipient_id,
                "template": template_name,
                "language": language,
                "parameters": parameters or [],
                "type": "template",
            }
        )
        logger.info(
            "[mock:%s] template=%s to=%s params=%s",
            self.channel,
            template_name,
            recipient_id,
            parameters,
        )
        return SendResult(ok=True, provider_message_id=message_id, status_code=200)


def chunk_text(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return [chunk for chunk in chunks if chunk]


def post_with_retry(
    url: str,
    payload: dict,
    headers: dict[str, str],
    timeout: float,
    max_attempts: int = 3,
) -> tuple[int | None, dict, str | None, int]:
    """POST with bounded exponential backoff for 429 and 5xx responses."""
    last_error: str | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, json=payload, headers=headers)
            try:
                body = response.json()
            except ValueError:
                body = {"raw": response.text[:500]}

            if 200 <= response.status_code < 300:
                return response.status_code, body, None, attempt

            last_error = f"HTTP {response.status_code}: {str(body)[:300]}"
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt == max_attempts:
                return response.status_code, body, last_error, attempt

            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = min(float(retry_after), 8.0)
                except ValueError:
                    delay = 0.8 * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
            else:
                delay = 0.8 * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
            logger.warning("Sender retry %d/%d in %.2fs: %s", attempt, max_attempts, delay, last_error)
            time.sleep(delay)
        except httpx.HTTPError as exc:
            last_error = f"transport_error: {exc}"
            if attempt == max_attempts:
                break
            delay = 0.8 * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
            logger.warning("Sender transport retry %d/%d in %.2fs", attempt, max_attempts, delay)
            time.sleep(delay)
    return None, {}, last_error, max_attempts
