from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


def compute_signature(raw_body: bytes, app_secret: str) -> str:
    digest = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_meta_signature(
    raw_body: bytes,
    signature_header: str | None,
    app_secret: str | None = None,
    allow_unsigned: bool | None = None,
) -> tuple[bool, str]:
    """Validate Meta's X-Hub-Signature-256 header.

    Returns (ok, reason) instead of raising so callers can choose a 401 or 403
    and log a useful reason. An empty secret is only accepted when the caller
    explicitly enables unsigned webhooks for local development.
    """
    secret = settings.app_secret if app_secret is None else app_secret
    unsigned_ok = settings.allow_unsigned_webhooks if allow_unsigned is None else allow_unsigned

    if not secret:
        if unsigned_ok:
            logger.warning("Webhook signature check bypassed: APP_SECRET is empty")
            return True, "unsigned_allowed"
        return False, "app_secret_not_configured"

    if not signature_header:
        return False, "missing_signature"
    if not signature_header.startswith("sha256="):
        return False, "unsupported_signature_scheme"

    expected = compute_signature(raw_body, secret)
    if not hmac.compare_digest(expected, signature_header):
        return False, "signature_mismatch"
    return True, "ok"


async def require_admin(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Protect dashboard/API routes when ADMIN_API_KEY is configured."""
    if not settings.admin_api_key:
        return
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )


def mask_identifier(value: str | None) -> str:
    if not value:
        return "unknown"
    if len(value) <= 4:
        return "***"
    return f"***{value[-4:]}"
