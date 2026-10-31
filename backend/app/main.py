from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import (
    analytics,
    conversations,
    feedback,
    handoffs,
    health,
    internal,
    model,
    portal,
    privacy,
)
from app.config import settings
from app.db import init_db
from app.logging_setup import configure_logging
from app.webhooks.router import router as webhook_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    init_db()
    logger.info(
        "Starting %s env=%s queue=%s outbound=%s nlu=%s",
        settings.app_name,
        settings.environment,
        settings.queue_backend,
        settings.outbound_mode,
        settings.nlu_backend,
    )
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Instagram + WhatsApp auto-reply service with transformer NLU, grounded FAQ "
        "retrieval, human handoff, analytics, and a feedback loop."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "%s %s status=%s duration_ms=%.1f request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )
    return response


app.include_router(webhook_router)
app.include_router(health.router)
app.include_router(conversations.router)
app.include_router(handoffs.router)
app.include_router(analytics.router)
app.include_router(feedback.router)
app.include_router(privacy.router)
app.include_router(model.router)
app.include_router(internal.router)
app.include_router(portal.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "webhooks": {
            "whatsapp": "/webhook/whatsapp",
            "instagram": "/webhook/instagram",
        },
        "dashboard_api": "/api/conversations",
        "portal": "/api/portal/auth/login",
    }
