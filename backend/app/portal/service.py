from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime

import httpx
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    ChannelConnection,
    Conversation,
    PortalEvent,
    PortalSession,
    PortalUser,
    Tenant,
    utcnow,
)
from app.portal.crypto import (
    CryptoError,
    decrypt_secret,
    encrypt_secret,
    expires_in,
    hash_otp,
    hash_password,
    hash_token,
    new_otp,
    new_session_token,
    normalize_email,
    normalize_phone,
    otp_matches,
    verify_password,
)
from app.senders.factory import get_sender

logger = logging.getLogger(__name__)

SUPPORTED_PORTAL_CHANNELS = ("whatsapp", "instagram")


class PortalError(ValueError):
    """A safe, user-facing portal error."""


# --- accounts ----------------------------------------------------------------


def _slug_base(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:80] or "workspace"


def unique_slug(db: Session, name: str) -> str:
    base = _slug_base(name)
    candidate = base
    while db.scalar(select(Tenant.id).where(Tenant.slug == candidate)):
        candidate = f"{base[:70]}-{secrets.token_hex(3)}"
    return candidate


def register_tenant(
    db: Session,
    *,
    business_name: str,
    full_name: str,
    email: str | None,
    phone: str | None,
    password: str,
    welcome_opt_in: bool,
) -> tuple[Tenant, PortalUser]:
    if len(password) < settings.portal_password_min_length:
        raise PortalError(
            f"Use at least {settings.portal_password_min_length} characters for the password"
        )
    email = normalize_email(email)
    phone = normalize_phone(phone)
    if not email and not phone:
        raise PortalError("Provide an email address or a phone number")

    if email and db.scalar(select(PortalUser.id).where(PortalUser.email == email)):
        raise PortalError("An account with that email already exists")
    if phone and db.scalar(select(PortalUser.id).where(PortalUser.phone == phone)):
        raise PortalError("An account with that phone number already exists")

    tenant = Tenant(name=business_name.strip(), slug=unique_slug(db, business_name))
    db.add(tenant)
    db.flush()

    user = PortalUser(
        tenant_id=tenant.id,
        email=email,
        phone=phone,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        role="owner",
        welcome_opt_in=welcome_opt_in,
        welcome_opt_in_at=utcnow() if welcome_opt_in else None,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise PortalError("An account with that email or phone already exists") from exc
    _record_event(
        db,
        tenant_id=tenant.id,
        user_id=user.id,
        event_type="account_registered",
        status="ok",
        detail={"welcome_opt_in": welcome_opt_in},
    )
    return tenant, user


def authenticate(db: Session, identifier: str, password: str) -> PortalUser | None:
    identifier = identifier.strip()
    email = normalize_email(identifier) if "@" in identifier else None
    conditions = []
    if email:
        conditions.append(PortalUser.email == email)
    try:
        phone = normalize_phone(identifier) if not email else None
    except ValueError:
        phone = None
    if phone:
        conditions.append(PortalUser.phone == phone)
    if not conditions:
        return None
    user = db.scalar(select(PortalUser).where(or_(*conditions)))
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_session(
    db: Session, user: PortalUser, *, ip_address: str | None, user_agent: str | None
) -> tuple[PortalSession, str]:
    token = new_session_token()
    session = PortalSession(
        token_hash=hash_token(token),
        user_id=user.id,
        tenant_id=user.tenant_id,
        expires_at=expires_in(settings.portal_session_hours * 3600),
        ip_address=(ip_address or "")[:64] or None,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(session)
    db.flush()
    return session, token


def revoke_session(db: Session, session: PortalSession) -> None:
    session.revoked_at = utcnow()
    db.flush()


# --- channel connections -----------------------------------------------------


@dataclass(slots=True)
class OAuthTokens:
    access_token: str
    expires_in: int | None = None
    scopes: str | None = None


def _graph_url(path: str) -> str:
    return (
        f"{settings.graph_base_url.rstrip('/')}/{settings.whatsapp_api_version}/{path.lstrip('/')}"
    )


def exchange_oauth_code(code: str) -> OAuthTokens:
    if not settings.portal_meta_configured:
        raise PortalError(
            "Meta OAuth is not configured. Set PORTAL_META_APP_ID and "
            "PORTAL_META_APP_SECRET, or use the local demo connection."
        )
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                _graph_url("oauth/access_token"),
                params={
                    "client_id": settings.portal_meta_app_id,
                    "client_secret": settings.portal_meta_app_secret,
                    "redirect_uri": settings.portal_oauth_redirect,
                    "code": code,
                },
            )
    except httpx.HTTPError as exc:
        raise PortalError(f"Could not reach Meta: {exc}") from exc
    if response.status_code >= 400:
        raise PortalError("Meta rejected the authorization code")
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise PortalError("Meta did not return an access token")
    return OAuthTokens(
        access_token=str(token),
        expires_in=int(payload["expires_in"]) if payload.get("expires_in") else None,
        scopes=payload.get("scope"),
    )


def verify_channel_account(channel: str, token: str, external_account_id: str) -> dict:
    fields = "id,display_phone_number,verified_name" if channel == "whatsapp" else "id,username"
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                _graph_url(external_account_id),
                params={"fields": fields, "access_token": token},
            )
    except httpx.HTTPError as exc:
        raise PortalError(f"Could not reach Meta: {exc}") from exc
    if response.status_code >= 400:
        raise PortalError("Meta could not verify that account with the new token")
    return response.json()


def connect_channel(
    db: Session,
    *,
    tenant: Tenant,
    user: PortalUser,
    channel: str,
    mode: str,
    authorization_code: str | None,
    external_account_id: str | None,
    display_name: str | None,
    waba_id: str | None,
    scopes: str | None,
) -> ChannelConnection:
    if channel not in SUPPORTED_PORTAL_CHANNELS:
        raise PortalError("Unsupported channel")

    existing = db.scalar(
        select(ChannelConnection).where(
            ChannelConnection.tenant_id == tenant.id,
            ChannelConnection.channel == channel,
        )
    )

    if mode == "demo":
        if not settings.portal_mock_connect_allowed:
            raise PortalError("Demo channel connections are disabled")
        if not external_account_id:
            raise PortalError("external_account_id is required")
        token = f"demo-{channel}-{secrets.token_urlsafe(12)}"
        account_id = external_account_id.strip()
        display_name = display_name or f"Demo {channel.title()} account"
        account_meta = {"demo": True}
        token_expires_at = None
        scopes = "demo"
    else:
        if not authorization_code:
            raise PortalError("authorization_code is required")
        tokens = exchange_oauth_code(authorization_code)
        token = tokens.access_token
        scopes = scopes or tokens.scopes
        token_expires_at = expires_in(tokens.expires_in) if tokens.expires_in else None
        if channel == "instagram" and not external_account_id:
            raise PortalError("Instagram requires the connected IG account id")
        if channel == "whatsapp" and not external_account_id:
            raise PortalError("WhatsApp requires the connected phone number id")
        account_id = external_account_id.strip()
        account_meta = verify_channel_account(channel, token, account_id)
        if not display_name:
            display_name = (
                account_meta.get("verified_name") or account_meta.get("username") or account_id
            )
        if waba_id:
            account_meta["waba_id"] = waba_id

    collision = db.scalar(
        select(ChannelConnection).where(
            ChannelConnection.channel == channel,
            ChannelConnection.external_account_id == account_id,
        )
    )
    if collision and collision.tenant_id != tenant.id:
        raise PortalError("That channel account is already connected to another workspace")

    if existing:
        connection = existing
        connection.external_account_id = account_id
        connection.display_name = display_name
        connection.status = "connected"
        connection.access_token_cipher = encrypt_secret(token)
        connection.token_expires_at = token_expires_at
        connection.scopes = scopes
        connection.meta = account_meta
        connection.connected_by_user_id = user.id
        connection.connected_at = utcnow()
        connection.updated_at = utcnow()
    else:
        connection = ChannelConnection(
            tenant_id=tenant.id,
            channel=channel,
            external_account_id=account_id,
            display_name=display_name,
            status="connected",
            access_token_cipher=encrypt_secret(token),
            token_expires_at=token_expires_at,
            scopes=scopes,
            meta=account_meta,
            connected_by_user_id=user.id,
        )
        db.add(connection)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise PortalError("That channel account is already connected") from exc

    _record_event(
        db,
        tenant_id=tenant.id,
        user_id=user.id,
        event_type="channel_connected",
        status="ok",
        channel=channel,
        detail={"account": display_name, "mode": mode},
    )
    return connection


def disconnect_channel(db: Session, tenant: Tenant, channel: str) -> None:
    connection = db.scalar(
        select(ChannelConnection).where(
            ChannelConnection.tenant_id == tenant.id,
            ChannelConnection.channel == channel,
        )
    )
    if not connection:
        raise PortalError("That channel is not connected")
    db.delete(connection)
    _record_event(
        db,
        tenant_id=tenant.id,
        event_type="channel_disconnected",
        status="ok",
        channel=channel,
    )
    db.flush()


def connection_for_channel(db: Session, tenant_id: str, channel: str) -> ChannelConnection | None:
    return db.scalar(
        select(ChannelConnection).where(
            ChannelConnection.tenant_id == tenant_id,
            ChannelConnection.channel == channel,
            ChannelConnection.status == "connected",
        )
    )


def resolve_tenant_for_account(db: Session, channel: str, account_id: str | None) -> str | None:
    """Map an inbound webhook's business account to a workspace."""
    if not account_id:
        return None
    return db.scalar(
        select(ChannelConnection.tenant_id).where(
            ChannelConnection.channel == channel,
            ChannelConnection.external_account_id == str(account_id),
            ChannelConnection.status == "connected",
        )
    )


# --- activation and notifications --------------------------------------------


def _record_event(
    db: Session,
    *,
    tenant_id: str,
    event_type: str,
    status: str,
    user_id: str | None = None,
    session_id: str | None = None,
    channel: str | None = None,
    detail: dict | None = None,
) -> PortalEvent:
    event = PortalEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        event_type=event_type,
        status=status,
        channel=channel,
        detail=detail or {},
    )
    db.add(event)
    return event


def _send_whatsapp_template(
    db: Session,
    tenant: Tenant,
    recipient: str,
    *,
    template: str,
    language: str,
    parameters: list[str],
):
    connection = connection_for_channel(db, tenant.id, "whatsapp")
    if not connection:
        return None, "whatsapp_not_connected"
    try:
        token = decrypt_secret(connection.access_token_cipher)
    except CryptoError:
        logger.exception("Cannot decrypt channel token tenant=%s", tenant.id)
        return None, "channel_token_unreadable"
    if not token:
        return None, "channel_token_missing"
    sender = get_sender(
        "whatsapp",
        token,
        connection.external_account_id,
        demo=bool((connection.meta or {}).get("demo")),
    )
    result = sender.send_template(recipient, template, language, parameters)
    return result, None if result.ok else (result.error or "send_failed")


def activation_for_login(
    db: Session,
    *,
    tenant: Tenant,
    user: PortalUser,
    session: PortalSession,
) -> dict:
    """Activate automation and (when allowed) send the login confirmation.

    A business-initiated message requires opt-in, a verified phone number, a
    connected WhatsApp account, and a Meta-approved template. Anything less is
    recorded as blocked instead of quietly dropping the requirement.
    """
    tenant.automation_enabled = True
    if not tenant.activated_at:
        tenant.activated_at = utcnow()
    user.last_login_at = utcnow()

    _record_event(
        db,
        tenant_id=tenant.id,
        user_id=user.id,
        session_id=session.id,
        event_type="automation_activated",
        status="ok",
        detail={"via": "portal_login"},
    )

    def blocked(reason: str) -> dict:
        _record_event(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            session_id=session.id,
            event_type="welcome_message",
            status="blocked",
            channel="whatsapp",
            detail={"reason": reason},
        )
        return {"status": "blocked", "reason": reason, "channel": "whatsapp"}

    if not settings.portal_welcome_template_name:
        return blocked("welcome_template_not_configured")
    if not user.welcome_opt_in:
        return blocked("welcome_opt_in_required")
    if not user.phone:
        return blocked("phone_number_missing")
    if not user.phone_verified:
        return blocked("phone_not_verified")

    parameters = [
        user.full_name.split()[0] if user.full_name else "there",
        tenant.name,
        utcnow().strftime("%d %b %Y, %H:%M UTC"),
    ]
    result, error = _send_whatsapp_template(
        db,
        tenant,
        user.phone,
        template=settings.portal_welcome_template_name,
        language=settings.portal_welcome_template_language,
        parameters=parameters,
    )
    if result is None:
        return blocked(error or "whatsapp_not_connected")

    _record_event(
        db,
        tenant_id=tenant.id,
        user_id=user.id,
        session_id=session.id,
        event_type="welcome_message",
        status="sent" if result.ok else "failed",
        channel="whatsapp",
        detail={
            "template": settings.portal_welcome_template_name,
            "error": error,
            "provider_message_id": result.provider_message_id,
        },
    )
    if result.ok:
        return {"status": "sent", "reason": None, "channel": "whatsapp"}
    return {"status": "failed", "reason": error or "send_failed", "channel": "whatsapp"}


def notify_assignment(
    db: Session, conversation: Conversation, agent: str | None
) -> PortalEvent | None:
    """Notify a portal teammate when a conversation is assigned to them."""
    if not conversation.tenant_id or not agent:
        return None
    tenant = db.get(Tenant, conversation.tenant_id)
    if not tenant:
        return None

    needle = agent.strip()
    user = db.scalar(
        select(PortalUser).where(
            PortalUser.tenant_id == tenant.id,
            PortalUser.is_active.is_(True),
            or_(
                PortalUser.email == needle.lower(),
                PortalUser.phone == needle,
                PortalUser.full_name.ilike(needle),
            ),
        )
    )
    if not user:
        return None

    detail = {"conversation_id": conversation.id, "agent": agent}
    if not user.welcome_opt_in or not user.phone_verified or not user.phone:
        event = _record_event(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            event_type="assignment_notification",
            status="blocked",
            channel="whatsapp",
            detail={**detail, "reason": "notification_consent_missing"},
        )
        db.flush()
        return event

    parameters = [
        user.full_name.split()[0] if user.full_name else "there",
        conversation.customer.display_name or "a customer",
        conversation.channel.title(),
    ]
    result, error = _send_whatsapp_template(
        db,
        tenant,
        user.phone,
        template=settings.portal_assignment_template_name,
        language=settings.portal_assignment_template_language,
        parameters=parameters,
    )
    event = _record_event(
        db,
        tenant_id=tenant.id,
        user_id=user.id,
        event_type="assignment_notification",
        status="sent" if result and result.ok else "blocked" if result is None else "failed",
        channel="whatsapp",
        detail={
            **detail,
            "template": settings.portal_assignment_template_name,
            "reason": error,
            "provider_message_id": result.provider_message_id if result else None,
        },
    )
    db.flush()
    return event


# --- phone verification ------------------------------------------------------


def set_phone_number(db: Session, user: PortalUser, *, phone: str, password: str) -> PortalUser:
    """Attach or replace the notification phone number.

    Requires the current password so a borrowed session cannot quietly redirect
    proactive messages. A changed number always loses its verified status.
    """
    if not verify_password(password, user.password_hash):
        raise PortalError("That password is not correct")
    normalized = normalize_phone(phone)
    if normalized == user.phone:
        return user
    if db.scalar(
        select(PortalUser.id).where(PortalUser.phone == normalized, PortalUser.id != user.id)
    ):
        raise PortalError("That phone number is already used by another account")

    user.phone = normalized
    user.phone_verified = False
    user.phone_verified_at = None
    user.otp_hash = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    _record_event(
        db,
        tenant_id=user.tenant_id,
        user_id=user.id,
        event_type="phone_updated",
        status="ok",
        detail={"phone_last4": normalized[-4:]},
    )
    db.flush()
    return user


def request_phone_verification(db: Session, user: PortalUser) -> dict:
    if user.phone_verified:
        return {"status": "already_verified", "phone": user.phone}
    if not user.phone:
        return {"status": "unavailable", "message": "Add a phone number first."}
    if settings.portal_otp_delivery == "disabled":
        return {
            "status": "unavailable",
            "message": "Phone verification is not configured on this deployment.",
        }

    remaining = seconds_until(user.otp_expires_at)
    if (
        user.otp_hash
        and remaining is not None
        and remaining > max(0, settings.portal_otp_ttl_seconds - 30)
    ):
        return {
            "status": "rate_limited",
            "phone": user.phone,
            "message": "Wait a moment before requesting another code.",
        }

    code = new_otp()
    user.otp_hash = hash_otp(code, user.phone)
    user.otp_expires_at = expires_in(settings.portal_otp_ttl_seconds)
    user.otp_attempts = 0

    if settings.portal_otp_delivery == "webhook":
        if not settings.portal_otp_webhook_url:
            return {
                "status": "unavailable",
                "message": "OTP delivery webhook is not configured.",
            }
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    settings.portal_otp_webhook_url,
                    json={"phone": user.phone, "code": code, "purpose": "portal_verify"},
                )
            if response.status_code >= 400:
                return {"status": "unavailable", "message": "Could not send the code."}
        except httpx.HTTPError:
            logger.exception("OTP webhook failed for phone=%s", user.phone[-4:])
            return {"status": "unavailable", "message": "Could not send the code."}
        return {"status": "sent", "phone": user.phone}

    return {
        "status": "sent",
        "phone": user.phone,
        "dev_code": code,
        "message": "Development mode: use this code to verify the number.",
    }


def confirm_phone_verification(db: Session, user: PortalUser, code: str) -> None:
    if user.phone_verified:
        return
    if not user.phone or not user.otp_hash or not user.otp_expires_at:
        raise PortalError("Request a new verification code")
    if user.otp_expires_at < utcnow():
        raise PortalError("That code has expired. Request a new one.")
    if user.otp_attempts >= settings.portal_otp_max_attempts:
        raise PortalError("Too many attempts. Request a new code.")
    if not otp_matches(code, user.phone, user.otp_hash):
        user.otp_attempts += 1
        raise PortalError("That code is not correct")
    user.phone_verified = True
    user.phone_verified_at = utcnow()
    user.otp_hash = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    _record_event(
        db,
        tenant_id=user.tenant_id,
        user_id=user.id,
        event_type="phone_verified",
        status="ok",
        detail={"phone_last4": user.phone[-4:]},
    )


def seconds_until(expires_at: datetime | None) -> int | None:
    if not expires_at:
        return None
    return max(0, int((expires_at - utcnow()).total_seconds()))
