from __future__ import annotations

import logging
from functools import lru_cache

from app.config import settings
from app.senders.base import BaseSender, MockSender
from app.senders.instagram import InstagramSender
from app.senders.whatsapp import WhatsAppSender

logger = logging.getLogger(__name__)


def get_sender(
    channel: str,
    token: str | None = None,
    account_id: str | None = None,
    demo: bool = False,
) -> BaseSender:
    """Return a sender for a channel.

    Without a tenant token the process-wide, cached sender is used. A tenant
    token always produces a fresh sender so workspaces cannot leak credentials
    into each other. Demo connections are always mock senders: a local demo
    token must never be presented to Meta.
    """
    if not token:
        return _cached_sender(channel)
    if demo or settings.outbound_mode == "mock":
        return MockSender(channel)

    if channel == "whatsapp":
        if account_id:
            return WhatsAppSender(token=token, phone_number_id=account_id)
        logger.warning("Tenant WhatsApp connection is missing its phone_number_id")
        return MockSender(channel)
    if channel == "instagram":
        return InstagramSender(token=token)
    raise ValueError(f"Unsupported channel: {channel}")


@lru_cache
def _cached_sender(channel: str) -> BaseSender:
    if settings.outbound_mode == "mock":
        logger.info("Outbound mode is mock for %s", channel)
        return MockSender(channel)

    if channel == "whatsapp":
        if settings.whatsapp_token and settings.phone_number_id:
            return WhatsAppSender()
        logger.warning("WhatsApp credentials missing; using mock sender")
        return MockSender(channel)

    if channel == "instagram":
        if settings.ig_page_token:
            return InstagramSender()
        logger.warning("Instagram credentials missing; using mock sender")
        return MockSender(channel)

    raise ValueError(f"Unsupported channel: {channel}")
