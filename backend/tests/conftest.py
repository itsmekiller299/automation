from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
with tempfile.NamedTemporaryFile(
    prefix="autoreply-test-", suffix=".db", delete=False
) as _temp_db:
    TEMP_DB = Path(_temp_db.name)

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"sqlite:///{TEMP_DB}",
        "REDIS_URL": "redis://127.0.0.1:6399/0",
        "QUEUE_BACKEND": "inline",
        "OUTBOUND_MODE": "mock",
        "NLU_BACKEND": "rules",
        "RAG_BACKEND": "lexical",
        "LLM_PROVIDER": "template",
        "LLM_API_KEY": "",
        "EMBEDDING_LOCAL_ONLY": "true",
        "APP_SECRET": "test-app-secret",
        "VERIFY_TOKEN": "test-verify-token",
        "ALLOW_UNSIGNED_WEBHOOKS": "false",
        "ADMIN_API_KEY": "",
        "ORDERS_API_URL": "",
        "LOG_LEVEL": "WARNING",
    }
)

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.dialogue.manager import DialogueManager  # noqa: E402
from app.llm.base import TemplateProvider  # noqa: E402
from app.main import app  # noqa: E402
from app.nlu.types import NLUResult  # noqa: E402
from app.rag.store import FAQStore  # noqa: E402
from app.services.orders import OrdersClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def faq_store():
    return FAQStore(path=ROOT / "ml" / "data" / "faqs.jsonl", backend="lexical")


@pytest.fixture()
def manager(faq_store):
    return DialogueManager(
        faq_store=faq_store,
        orders_client=OrdersClient(base_url="", fixture_path=ROOT / "ml" / "data" / "orders.json"),
        llm=TemplateProvider(),
        threshold=0.80,
        max_fallbacks=2,
        max_attempts=2,
    )


@pytest.fixture()
def conversation():
    return SimpleNamespace(
        id="cnv_test",
        channel="whatsapp",
        status="bot",
        bot_identified=False,
        customer=SimpleNamespace(display_name="Siva", external_id="919900000001", opted_in=True),
    )


@pytest.fixture()
def state():
    from app.dialogue.session import SessionState

    return SessionState()


def make_nlu(intent="greeting", confidence=0.9, entities=None):
    return NLUResult(
        intent=intent,
        confidence=confidence,
        entities=entities or [],
        top_intents=[{"intent": intent, "confidence": confidence}],
        model_version="test",
        source="rules",
    )


@pytest.fixture()
def nlu_factory():
    return make_nlu
