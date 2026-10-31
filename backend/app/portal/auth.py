from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.db import get_db
from app.models import PortalSession, PortalUser, Tenant, utcnow
from app.portal.crypto import hash_token

COOKIE_NAME = "orbit_portal_session"


@dataclass(slots=True)
class PortalContext:
    user: PortalUser
    tenant: Tenant
    session: PortalSession

    @property
    def tenant_id(self) -> str:
        return self.tenant.id


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def require_portal_user(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
    orbit_portal_session: Annotated[str | None, Cookie()] = None,
) -> PortalContext:
    if not settings.portal_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal disabled")

    token = _bearer(authorization) or orbit_portal_session
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session = db.scalar(
        select(PortalSession)
        .options(
            joinedload(PortalSession.user).joinedload(PortalUser.tenant),
        )
        .where(PortalSession.token_hash == hash_token(token))
    )
    if (
        not session
        or session.revoked_at is not None
        or session.expires_at < utcnow()
        or not session.user
        or not session.user.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    tenant = session.user.tenant
    if not tenant or tenant.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace is inactive")
    return PortalContext(user=session.user, tenant=tenant, session=session)
