from __future__ import annotations

import logging
import threading
import time
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import (
    ChannelConnection,
    PortalEvent,
    PortalUser,
    Tenant,
)
from app.portal.auth import COOKIE_NAME, PortalContext, require_portal_user
from app.portal.crypto import sign_oauth_state, verify_oauth_state
from app.portal.schemas import (
    ActivationOut,
    AuthOut,
    ChannelConnectIn,
    ChannelOut,
    LoginIn,
    MeOut,
    OAuthUrlOut,
    PhoneUpdateIn,
    PhoneVerificationOut,
    PortalConfigOut,
    PortalEventOut,
    PortalUserOut,
    RegisterIn,
    TenantOut,
    VerifyPhoneIn,
)
from app.portal.service import (
    PortalError,
    activation_for_login,
    authenticate,
    confirm_phone_verification,
    connect_channel,
    create_session,
    disconnect_channel,
    register_tenant,
    request_phone_verification,
    revoke_session,
    set_phone_number,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portal", tags=["portal"])

# Single-process limiter. Swap for Redis when running multiple API replicas.
_attempts: dict[str, list[float]] = {}
_attempts_lock = threading.Lock()


def _rate_limited(identifier: str) -> bool:
    key = identifier.strip().lower()
    now = time.monotonic()
    window = settings.portal_login_window_seconds
    with _attempts_lock:
        recent = [stamp for stamp in _attempts.get(key, []) if now - stamp < window]
        if recent:
            _attempts[key] = recent
        else:
            _attempts.pop(key, None)
        return len(recent) >= settings.portal_login_max_attempts


def _record_failure(identifier: str) -> None:
    key = identifier.strip().lower()
    with _attempts_lock:
        _attempts.setdefault(key, []).append(time.monotonic())


def _clear_failures(identifier: str) -> None:
    with _attempts_lock:
        _attempts.pop(identifier.strip().lower(), None)


def _user_out(user: PortalUser) -> PortalUserOut:
    return PortalUserOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        welcome_opt_in=user.welcome_opt_in,
        phone_verified=user.phone_verified,
        last_login_at=user.last_login_at,
    )


def _tenant_out(tenant: Tenant) -> TenantOut:
    return TenantOut(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        plan=tenant.plan,
        automation_enabled=tenant.automation_enabled,
        activated_at=tenant.activated_at,
    )


def _channel_out(connection: ChannelConnection) -> ChannelOut:
    return ChannelOut(
        channel=connection.channel,
        external_account_id=connection.external_account_id,
        display_name=connection.display_name,
        status=connection.status,
        connected_at=connection.connected_at,
        token_expires_at=connection.token_expires_at,
    )


def _event_out(event: PortalEvent) -> PortalEventOut:
    return PortalEventOut(
        id=event.id,
        event_type=event.event_type,
        status=event.status,
        channel=event.channel,
        detail=event.detail or {},
        created_at=event.created_at,
    )


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.portal_session_hours * 3600,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


def _auth_response(
    *,
    user: PortalUser,
    tenant: Tenant,
    session,
    token: str,
    activation: dict | None,
    response: Response,
) -> AuthOut:
    _set_cookie(response, token)
    return AuthOut(
        token=token,
        expires_at=session.expires_at,
        user=_user_out(user),
        tenant=_tenant_out(tenant),
        activation=ActivationOut(**activation) if activation else None,
        phone_verification_required=bool(user.phone and not user.phone_verified),
    )


@router.get("/config", response_model=PortalConfigOut)
def portal_config() -> PortalConfigOut:
    return PortalConfigOut(
        enabled=settings.portal_enabled,
        meta_oauth_configured=settings.portal_meta_configured,
        mock_channel_connect=settings.portal_mock_connect_allowed,
        welcome_template=settings.portal_welcome_template_name,
        brand=settings.brand_name,
    )


@router.post("/auth/register", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterIn,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthOut:
    if not settings.portal_enabled:
        raise HTTPException(status_code=404, detail="Portal disabled")
    try:
        tenant, user = register_tenant(
            db,
            business_name=body.business_name,
            full_name=body.full_name,
            email=body.email,
            phone=body.phone,
            password=body.password,
            welcome_opt_in=body.welcome_opt_in,
        )
    except PortalError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        logger.exception("Portal registration failed")
        raise HTTPException(status_code=500, detail="Could not create the account") from None

    session, token = create_session(
        db,
        user,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    activation = activation_for_login(db, tenant=tenant, user=user, session=session)
    db.commit()
    return _auth_response(
        user=user,
        tenant=tenant,
        session=session,
        token=token,
        activation=activation,
        response=response,
    )


@router.post("/auth/login", response_model=AuthOut)
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthOut:
    if not settings.portal_enabled:
        raise HTTPException(status_code=404, detail="Portal disabled")
    if _rate_limited(body.identifier):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts. Try again later.",
        )

    user = authenticate(db, body.identifier, body.password)
    if not user:
        _record_failure(body.identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect account or password",
        )
    _clear_failures(body.identifier)

    tenant = db.get(Tenant, user.tenant_id)
    if not tenant or tenant.status != "active":
        raise HTTPException(status_code=403, detail="Workspace is inactive")

    session, token = create_session(
        db,
        user,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    activation = activation_for_login(db, tenant=tenant, user=user, session=session)
    db.commit()
    logger.info(
        "Portal login tenant=%s user=%s activation=%s",
        tenant.id,
        user.id,
        activation.get("status"),
    )
    return _auth_response(
        user=user,
        tenant=tenant,
        session=session,
        token=token,
        activation=activation,
        response=response,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    ctx: Annotated[PortalContext, Depends(require_portal_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    revoke_session(db, ctx.session)
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeOut)
def me(
    ctx: Annotated[PortalContext, Depends(require_portal_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeOut:
    channels = db.scalars(
        select(ChannelConnection)
        .where(ChannelConnection.tenant_id == ctx.tenant_id)
        .order_by(ChannelConnection.channel)
    ).all()
    events = db.scalars(
        select(PortalEvent)
        .where(PortalEvent.tenant_id == ctx.tenant_id)
        .order_by(PortalEvent.created_at.desc())
        .limit(20)
    ).all()
    return MeOut(
        user=_user_out(ctx.user),
        tenant=_tenant_out(ctx.tenant),
        channels=[_channel_out(connection) for connection in channels],
        recent_events=[_event_out(event) for event in events],
    )


@router.post("/phone", response_model=MeOut)
def update_phone(
    body: PhoneUpdateIn,
    ctx: Annotated[PortalContext, Depends(require_portal_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeOut:
    try:
        set_phone_number(db, ctx.user, phone=body.phone, password=body.password)
    except PortalError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return me(ctx, db)


@router.post("/phone/verification/request", response_model=PhoneVerificationOut)
def request_verification(
    ctx: Annotated[PortalContext, Depends(require_portal_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PhoneVerificationOut:
    result = request_phone_verification(db, ctx.user)
    db.commit()
    return PhoneVerificationOut(**result)


@router.post("/phone/verification/confirm", response_model=MeOut)
def confirm_verification(
    body: VerifyPhoneIn,
    ctx: Annotated[PortalContext, Depends(require_portal_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeOut:
    try:
        confirm_phone_verification(db, ctx.user, body.code)
    except PortalError as exc:
        db.commit()  # persist the failed-attempt counter
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return me(ctx, db)


@router.get("/channels", response_model=list[ChannelOut])
def list_channels(
    ctx: Annotated[PortalContext, Depends(require_portal_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ChannelOut]:
    channels = db.scalars(
        select(ChannelConnection)
        .where(ChannelConnection.tenant_id == ctx.tenant_id)
        .order_by(ChannelConnection.channel)
    ).all()
    return [_channel_out(connection) for connection in channels]


@router.get("/channels/oauth-url", response_model=OAuthUrlOut)
def oauth_url(
    channel: str,
    ctx: Annotated[PortalContext, Depends(require_portal_user)],
) -> OAuthUrlOut:
    if channel not in ("whatsapp", "instagram"):
        raise HTTPException(status_code=404, detail="Unsupported channel")
    if not settings.portal_meta_configured:
        return OAuthUrlOut(
            channel=channel,
            configured=False,
            mock_allowed=settings.portal_mock_connect_allowed,
            message=(
                "Meta OAuth is not configured on this deployment. Add "
                "PORTAL_META_APP_ID and PORTAL_META_APP_SECRET."
            ),
        )
    state = sign_oauth_state(
        {
            "sub": ctx.user.id,
            "tid": ctx.tenant_id,
            "channel": channel,
        }
    )
    scopes = (
        "whatsapp_business_management,whatsapp_business_messaging,business_management"
        if channel == "whatsapp"
        else "instagram_basic,instagram_manage_messages,pages_show_list,pages_manage_metadata,pages_messaging"
    )
    params = {
        "client_id": settings.portal_meta_app_id,
        "redirect_uri": settings.portal_oauth_redirect,
        "state": state,
        "response_type": "code",
    }
    if settings.portal_meta_config_id:
        params["config_id"] = settings.portal_meta_config_id
    else:
        params["scope"] = scopes
    url = (
        f"https://www.facebook.com/{settings.whatsapp_api_version}/dialog/oauth?{urlencode(params)}"
    )
    return OAuthUrlOut(
        channel=channel,
        configured=True,
        url=url,
        mock_allowed=settings.portal_mock_connect_allowed,
    )


@router.post("/channels/{channel}/connect", response_model=ChannelOut)
def connect(
    channel: str,
    body: ChannelConnectIn,
    ctx: Annotated[PortalContext, Depends(require_portal_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ChannelOut:
    if channel not in ("whatsapp", "instagram"):
        raise HTTPException(status_code=404, detail="Unsupported channel")

    if body.mode == "oauth":
        if not body.state:
            raise HTTPException(status_code=400, detail="Missing OAuth state")
        try:
            state = verify_oauth_state(body.state)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if (
            state.get("sub") != ctx.user.id
            or state.get("tid") != ctx.tenant_id
            or state.get("channel") != channel
        ):
            raise HTTPException(status_code=400, detail="OAuth state does not match this account")

    try:
        connection = connect_channel(
            db,
            tenant=ctx.tenant,
            user=ctx.user,
            channel=channel,
            mode=body.mode,
            authorization_code=body.authorization_code,
            external_account_id=body.external_account_id,
            display_name=body.display_name,
            waba_id=body.waba_id,
            scopes=body.scopes,
        )
    except PortalError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        logger.exception("Channel connect failed tenant=%s channel=%s", ctx.tenant_id, channel)
        raise HTTPException(status_code=502, detail="Could not connect the channel") from None
    db.commit()
    return _channel_out(connection)


@router.post("/channels/{channel}/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(
    channel: str,
    ctx: Annotated[PortalContext, Depends(require_portal_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    if channel not in ("whatsapp", "instagram"):
        raise HTTPException(status_code=404, detail="Unsupported channel")
    try:
        disconnect_channel(db, ctx.tenant, channel)
    except PortalError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/activity", response_model=list[PortalEventOut])
def activity(
    ctx: Annotated[PortalContext, Depends(require_portal_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[PortalEventOut]:
    events = db.scalars(
        select(PortalEvent)
        .where(PortalEvent.tenant_id == ctx.tenant_id)
        .order_by(PortalEvent.created_at.desc())
        .limit(limit)
    ).all()
    return [_event_out(event) for event in events]
