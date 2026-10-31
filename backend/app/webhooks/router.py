from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.queue import enqueue_messages
from app.security import verify_meta_signature
from app.webhooks.parsers import SUPPORTED_CHANNELS, parse_webhook, payload_fingerprint

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhooks"])


def _validate_channel(channel: str) -> str:
    if channel not in SUPPORTED_CHANNELS:
        raise HTTPException(status_code=404, detail="Unknown webhook channel")
    return channel


@router.get("/{channel}", response_class=PlainTextResponse)
def verify_handshake(
    channel: str,
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> PlainTextResponse:
    """Meta's GET subscription handshake."""
    _validate_channel(channel)
    if hub_mode != "subscribe":
        raise HTTPException(status_code=403, detail="Unsupported hub.mode")
    if not hub_verify_token or hub_verify_token != settings.verify_token:
        logger.warning("Webhook verification failed for channel=%s", channel)
        raise HTTPException(status_code=403, detail="Invalid verify token")
    return PlainTextResponse(content=hub_challenge or "")


@router.post("/{channel}")
async def receive_webhook(
    channel: str,
    request: Request,
    x_hub_signature_256: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> dict:
    """Validate, normalize, queue, and acknowledge a webhook immediately."""
    _validate_channel(channel)
    raw_body = await request.body()

    ok, reason = verify_meta_signature(raw_body, x_hub_signature_256)
    if not ok:
        logger.warning(
            "Rejected webhook channel=%s reason=%s bytes=%d", channel, reason, len(raw_body)
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception as exc:
        logger.warning("Malformed webhook JSON channel=%s: %s", channel, exc)
        raise HTTPException(status_code=400, detail="Malformed JSON payload") from exc

    try:
        messages = parse_webhook(channel, payload)
    except Exception:
        logger.exception("Webhook parse failure channel=%s", channel)
        # Acknowledge so Meta does not hammer us with a payload we cannot parse.
        return {"status": "ignored", "queued": 0}

    queued = 0
    if messages:
        try:
            enqueue_messages([message.to_dict() for message in messages])
            queued = len(messages)
        except Exception:
            logger.exception("Queue unavailable, asking Meta to retry channel=%s", channel)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Queue temporarily unavailable",
            ) from None

    logger.info(
        "Webhook accepted channel=%s fingerprint=%s messages=%d",
        channel,
        payload_fingerprint(payload),
        queued,
    )
    return {"status": "received", "queued": queued}
