from __future__ import annotations

from app.models import Conversation, Customer, Handoff
from app.nlu.sentiment import detect_frustration
from app.services.handoff import escalate, resolve_handoffs
from sqlalchemy import func, select

from shared.labels import CONVERSATION_NEEDS_HUMAN, HANDOFF_RESOLVED


def test_frustration_detection():
    flagged, terms = detect_frustration("This is absolutely useless. I want a refund.")
    assert flagged is True
    assert "useless" in terms

    flagged, _ = detect_frustration("Hi there, how are you?")
    assert flagged is False


def test_escalation_is_idempotent_and_pauses_bot(db):
    customer = Customer(channel="whatsapp", external_id="9199", display_name="Test")
    db.add(customer)
    db.flush()
    conversation = Conversation(customer_id=customer.id, channel="whatsapp")
    db.add(conversation)
    db.commit()

    first = escalate(db, conversation, "complaint", priority="normal")
    db.commit()
    assert conversation.status == CONVERSATION_NEEDS_HUMAN
    assert first.status == "open"

    second = escalate(db, conversation, "customer_requested_human", priority="high")
    db.commit()
    assert second.id == first.id
    assert second.priority == "high"
    assert db.scalar(select(func.count(Handoff.id))) == 1


def test_resolve_handoffs_marks_all_active(db):
    customer = Customer(channel="instagram", external_id="ig-1")
    db.add(customer)
    db.flush()
    conversation = Conversation(customer_id=customer.id, channel="instagram")
    db.add(conversation)
    db.commit()

    handoff = escalate(db, conversation, "low_confidence")
    db.commit()
    count = resolve_handoffs(db, conversation)
    db.commit()
    assert count == 1
    assert handoff.status == HANDOFF_RESOLVED
    assert handoff.resolved_at is not None
