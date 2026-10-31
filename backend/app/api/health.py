from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal
from app.llm.factory import get_llm_provider
from app.nlu.pipeline import get_nlu
from app.rag.store import get_faq_store

router = APIRouter(tags=["health"])


@router.get("/healthz")
def liveness() -> dict:
    return {"status": "ok", "service": settings.app_name}


@router.get("/health", include_in_schema=False)
def health_alias() -> dict:
    """Compatibility alias for platforms that probe /health by default."""
    return liveness()


@router.get("/readyz")
def readiness() -> dict:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc
    return {
        "status": "ready",
        "environment": settings.environment,
        "queue": settings.queue_backend,
        "outbound_mode": settings.outbound_mode,
        "nlu": get_nlu().version,
        "rag": get_faq_store().backend,
        "llm": get_llm_provider().name,
        "portal": "enabled" if settings.portal_enabled else "disabled",
        "portal_oauth": "configured" if settings.portal_meta_configured else "not_configured",
        "public_base_url": settings.public_base_url,
        "brand": settings.brand_name,
    }
