from __future__ import annotations

import json
import time

from app.db import SessionLocal
from app.models import Conversation, Customer, Handoff, Message, PredictionLog
from app.security import compute_signature
from sqlalchemy import select


def _whatsapp_payload(mid: str, text: str, sender: str = "919900000001") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "phone-1"},
                            "contacts": [
                                {"wa_id": sender, "profile": {"name": "Siva"}}
                            ],
                            "messages": [
                                {
                                    "from": sender,
                                    "id": mid,
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        }
                    }
                ],
            }
        ],
    }


def _post(client, payload: dict):
    raw = json.dumps(payload).encode()
    signature = compute_signature(raw, "test-app-secret")
    return client.post(
        "/webhook/whatsapp",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )


def test_webhook_end_to_end_order_status_and_deduplication(client):
    response = _post(client, _whatsapp_payload("wamid.e2e.1", "where is my order ORD-1042"))
    assert response.status_code == 200
    assert response.json()["queued"] == 1

    with SessionLocal() as db:
        conversation = db.scalar(select(Conversation))
        assert conversation is not None
        assert conversation.last_intent == "order_status"
        assert conversation.bot_identified is True
        messages = db.scalars(select(Message).order_by(Message.created_at)).all()
        assert [m.direction for m in messages] == ["inbound", "outbound"]
        assert "out for delivery" in messages[1].text.lower()
        assert messages[1].delivery_status == "sent"
        prediction = db.scalar(select(PredictionLog))
        assert prediction is not None
        assert prediction.intent == "order_status"

    duplicate = _post(client, _whatsapp_payload("wamid.e2e.1", "where is my order ORD-1042"))
    assert duplicate.status_code == 200
    with SessionLocal() as db:
        inbound = db.scalars(
            select(Message).where(Message.direction == "inbound")
        ).all()
        assert len(inbound) == 1


def test_complaint_creates_handoff_and_pauses_bot(client):
    response = _post(
        client,
        _whatsapp_payload("wamid.e2e.2", "This is unacceptable, my lamp arrived broken"),
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        conversation = db.scalar(select(Conversation))
        assert conversation.status == "needs_human"
        handoff = db.scalar(select(Handoff))
        assert handoff is not None
        assert handoff.reason == "complaint"
        before = db.scalar(select(Message.id).where(Message.direction == "outbound"))
        assert before is not None

    # The bot must not reply while the thread is paused.
    _post(client, _whatsapp_payload("wamid.e2e.3", "hello? are you there"))
    with SessionLocal() as db:
        outbound = db.scalars(select(Message).where(Message.direction == "outbound")).all()
        assert len(outbound) == 1
        inbound = db.scalars(select(Message).where(Message.direction == "inbound")).all()
        assert len(inbound) == 2


def test_feedback_privacy_and_analytics(client):
    _post(client, _whatsapp_payload("wamid.e2e.4", "where is my order ORD-1042"))

    with SessionLocal() as db:
        prediction = db.scalar(select(PredictionLog))
        assert prediction is not None
        prediction_id = prediction.id
        customer = db.scalar(select(Customer))
        customer_id = customer.id
        conversation_id = db.scalar(select(Conversation.id))

    feedback = client.post(
        f"/api/predictions/{prediction_id}/feedback",
        json={"corrected_intent": "order_status", "agent": "anika"},
    )
    assert feedback.status_code == 200
    assert feedback.json()["status"] == "queued_for_retraining"

    with SessionLocal() as db:
        inbound_message_id = db.scalar(
            select(Message.id).where(Message.direction == "inbound")
        )
    by_message = client.post(
        f"/api/messages/{inbound_message_id}/feedback",
        json={"corrected_intent": "pricing", "agent": "anika"},
    )
    assert by_message.status_code == 200
    assert by_message.json()["corrected_intent"] == "pricing"

    overview = client.get("/api/analytics/overview")
    assert overview.status_code == 200
    assert overview.json()["inbound_messages"] >= 1

    evaluation = client.get("/api/model/evaluation")
    assert evaluation.status_code == 200
    assert "available" in evaluation.json()

    detail = client.get(f"/api/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) >= 2

    deleted = client.post(
        "/api/privacy/delete",
        json={"customer_id": customer_id, "confirm": True},
    )
    assert deleted.status_code == 200
    with SessionLocal() as db:
        assert db.get(Customer, customer_id) is None
        assert db.scalars(select(Message)).all() == []
