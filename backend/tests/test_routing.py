from __future__ import annotations

from types import SimpleNamespace


def _handle(manager, conversation, state, nlu, text, message_type="text"):
    message = SimpleNamespace(text=text, message_type=message_type)
    return manager.handle(
        message,
        conversation,
        state,
        nlu,
        customer_name="Siva",
    )


def test_first_reply_discloses_automation(manager, conversation, state, nlu_factory):
    decision = _handle(
        manager, conversation, state, nlu_factory("greeting", 0.92), "hello"
    )
    assert decision.handoff is False
    assert "automated" in decision.reply.lower()
    assert "Aurora Living" in decision.reply


def test_no_disclosure_after_bot_identified(manager, conversation, state, nlu_factory):
    conversation.bot_identified = True
    decision = _handle(
        manager, conversation, state, nlu_factory("greeting", 0.92), "hello again"
    )
    assert "automated" not in decision.reply.lower()
    assert "How can I help" in decision.reply


def test_order_status_with_entity_uses_verified_orders_api(
    manager, conversation, state, nlu_factory
):
    entities = [{"type": "ORDER_ID", "value": "ORD-1042", "start": 20, "end": 28}]
    decision = _handle(
        manager,
        conversation,
        state,
        nlu_factory("order_status", 0.95, entities),
        "where is my order ORD-1042",
    )
    assert decision.handoff is False
    assert "out for delivery" in decision.reply.lower()
    assert "ORD-1042" in decision.reply
    assert decision.sources[0]["source"] == "orders_api"


def test_low_confidence_hands_off(manager, conversation, state, nlu_factory):
    decision = _handle(
        manager, conversation, state, nlu_factory("other", 0.55), "something vague"
    )
    assert decision.handoff is True
    assert decision.handoff_reason == "low_confidence"


def test_threshold_boundary_is_inclusive(manager, conversation, state, nlu_factory):
    conversation.bot_identified = True
    handled = _handle(manager, conversation, state, nlu_factory("greeting", 0.80), "hi")
    assert handled.handoff is False

    decision = _handle(manager, conversation, state, nlu_factory("greeting", 0.799), "hi")
    assert decision.handoff is True
    assert decision.handoff_reason == "low_confidence"


def test_complaint_escalates_with_high_priority(manager, conversation, state, nlu_factory):
    decision = _handle(
        manager,
        conversation,
        state,
        nlu_factory("complaint", 0.93),
        "my lamp arrived broken, this is unacceptable",
    )
    assert decision.handoff is True
    assert decision.handoff_reason == "complaint"
    assert decision.priority == "high"


def test_human_agent_request_escalates(manager, conversation, state, nlu_factory):
    decision = _handle(
        manager,
        conversation,
        state,
        nlu_factory("human_agent", 0.94),
        "I want to talk to a human",
    )
    assert decision.handoff is True
    assert decision.handoff_reason == "customer_requested_human"


def test_grounded_pricing_answer(manager, conversation, state, nlu_factory):
    decision = _handle(
        manager,
        conversation,
        state,
        nlu_factory("pricing", 0.92),
        "How much does the Aria Lamp cost?",
    )
    assert decision.handoff is False
    assert "$89" in decision.reply
    assert decision.sources
    assert "price" in decision.sources[0]["source"].lower()


def test_unverified_price_hands_off_instead_of_inventing(
    manager, conversation, state, nlu_factory
):
    decision = _handle(
        manager,
        conversation,
        state,
        nlu_factory("pricing", 0.92),
        "How much does the Cloud Sofa cost?",
    )
    assert decision.handoff is True
    assert decision.handoff_reason == "unverified_pricing"
    assert "$" not in decision.reply


def test_non_text_gets_text_prompt_then_handoff(
    manager, conversation, state, nlu_factory
):
    first = _handle(
        manager,
        conversation,
        state,
        nlu_factory("other", 0.2),
        "",
        message_type="image",
    )
    assert first.handoff is False
    assert "text messages" in first.reply.lower()

    second = _handle(
        manager,
        conversation,
        state,
        nlu_factory("other", 0.2),
        "",
        message_type="image",
    )
    assert second.handoff is True
    assert second.handoff_reason == "repeated_non_text"


def test_pending_order_slot_accepts_bare_order_id(
    manager, conversation, state, nlu_factory
):
    first = _handle(
        manager,
        conversation,
        state,
        nlu_factory("order_status", 0.9),
        "where is my order",
    )
    assert first.handoff is False
    assert "order ID" in first.reply
    assert state.pending_slot == "order_id"

    second = _handle(manager, conversation, state, nlu_factory("other", 0.3), "ORD-2048")
    assert second.handoff is False
    assert "ORD-2048" in second.reply
    assert "delivered" in second.reply.lower()
    assert state.pending_slot is None


def test_repeated_missing_order_id_hands_off(
    manager, conversation, state, nlu_factory
):
    _handle(
        manager, conversation, state, nlu_factory("order_status", 0.9), "where is my order"
    )
    decision = _handle(
        manager, conversation, state, nlu_factory("other", 0.3), "I don't know"
    )
    assert decision.handoff is True
    assert decision.handoff_reason == "missing_order_id"


def test_goodbye_resolves(manager, conversation, state, nlu_factory):
    decision = _handle(
        manager, conversation, state, nlu_factory("goodbye", 0.91), "thanks, bye"
    )
    assert decision.resolved is True
    assert decision.handoff is False


def test_frustration_overrides_topic(manager, conversation, state, nlu_factory):
    decision = _handle(
        manager,
        conversation,
        state,
        nlu_factory("order_status", 0.92),
        "this is useless, where is my order",
    )
    assert decision.handoff is True
    assert decision.handoff_reason == "customer_frustrated"
    assert decision.priority == "high"
