from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000
_PHONE_STRIP = re.compile(r"[\s().\-]")


class CryptoError(RuntimeError):
    pass


# --- passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "$".join(
        [
            PASSWORD_ALGORITHM,
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode(),
            base64.urlsafe_b64encode(digest).decode(),
        ]
    )


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored.split("$")
        if algorithm != PASSWORD_ALGORITHM:
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# --- sessions ----------------------------------------------------------------


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- secret storage ----------------------------------------------------------


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.portal_secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise CryptoError(
            "Channel token cannot be decrypted. Check PORTAL_ENCRYPTION_KEY."
        ) from exc


# --- one-time codes ----------------------------------------------------------


def new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str, phone: str) -> str:
    return hmac.new(
        settings.portal_secret.encode("utf-8"),
        f"otp:{phone}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()


def otp_matches(code: str, phone: str, stored: str | None) -> bool:
    if not stored:
        return False
    return hmac.compare_digest(hash_otp(code, phone), stored)


# --- identifiers -------------------------------------------------------------


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower()


def normalize_phone(value: str | None) -> str | None:
    """Normalize to +E.164-ish digits; reject obviously invalid input."""
    if not value:
        return None
    cleaned = _PHONE_STRIP.sub("", value.strip())
    if cleaned.startswith("00"):
        cleaned = f"+{cleaned[2:]}"
    digits = cleaned[1:] if cleaned.startswith("+") else cleaned
    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        raise ValueError("Enter a phone number in international format, e.g. +919900000001")
    return f"+{digits}"


# --- OAuth state -------------------------------------------------------------


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def sign_oauth_state(payload: dict, ttl_seconds: int = 900) -> str:
    body = {**payload, "exp": int(time.time()) + ttl_seconds}
    encoded = _b64encode(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        settings.portal_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{encoded}.{_b64encode(signature)}"


def verify_oauth_state(state: str) -> dict:
    try:
        encoded, signature_b64 = state.split(".", 1)
        signature = _b64decode(signature_b64)
    except (ValueError, TypeError) as exc:
        raise ValueError("Malformed OAuth state") from exc
    expected = hmac.new(
        settings.portal_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid OAuth state signature")
    payload = json.loads(_b64decode(encoded))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("OAuth state expired")
    return payload


# --- misc --------------------------------------------------------------------


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def expires_in(seconds: int) -> datetime:
    return utcnow() + timedelta(seconds=seconds)
