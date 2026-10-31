from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import settings
from app.dialogue.handlers import (
    bot_disclosure_prefix,
    is_pricing_chunk,
    knowledge_to_sources,
    lookup_error_answer,
    order_source,
    order_status_answer,
    orders_unavailable_answer,
    pricing_chunk_matches,
    return_policy_answer,
)
from app.dialogue.session import SessionState
from app.llm.base import GroundedContext
from app.llm.factory import get_llm_provider
from app.nlu.entities import extract_rule_entities, find_order_id, merge_entities
from app.nlu.sentiment import detect_frustration
from app.nlu.types import NLUResult
from app.rag.store import FAQStore, get_faq_store
from app.services.orders import OrdersClient, get_orders_client

logger = logging.getLogger(__name__)

NON_TEXT_REPLY = (
    "I can read text messages best. Please type your question, or ask for a human "
    "teammate if you need to send a photo or document."
)
CLARIFY_REPLY = (
    "I want to route this correctly. Are you asking about an order, a return or refund, "
    "a product, or pricing?"
)


@dataclass(slots=True)
class Decision:
    reply: str | None
    intent: str
    confidence: float
    entities: list[dict] = field(default_factory=list)
    top_intents: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    handoff: bool = False
    handoff_reason: str | None = None
    priority: str = "normal"
    resolved: bool = False
    model_version: str = "rules-v1"
    source: str = "rules"


class DialogueManager:
    def __init__(
        self,
        faq_store: FAQStore | None = None,
        orders_client: OrdersClient | None = None,
        llm=None,
        threshold: float | None = None,
        max_fallbacks: int | None = None,
        max_attempts: int | None = None,
    ) -> None:
        self.faq_store = faq_store or get_faq_store()
        self.orders_client = orders_client or get_orders_client()
        self.llm = llm or get_llm_provider()
        self.threshold = threshold if threshold is not None else settings.intent_confidence_threshold
        self.max_fallbacks = max_fallbacks if max_fallbacks is not None else settings.max_fallbacks
        self.max_attempts = max_attempts if max_attempts is not None else settings.max_window_attempts

    # ------------------------------------------------------------------ public
    def handle(
        self,
        message,
        conversation,
        state: SessionState,
        nlu: NLUResult,
        db: Session | None = None,
        customer_name: str | None = None,
    ) -> Decision:
        text = (getattr(message, "text", "") or "").strip()
        message_type = getattr(message, "message_type", "text") or "text"
        name = customer_name
        if name is None:
            customer = getattr(conversation, "customer", None)
            name = getattr(customer, "display_name", None)

        state.turn_count += 1
        state.bot_identified = bool(getattr(conversation, "bot_identified", state.bot_identified))

        if message_type not in {"text", "button", "interactive", "quick_reply", "postback"} and not text:
            state.non_text_count += 1
            if state.non_text_count >= self.max_attempts:
                return self._handoff(
                    conversation,
                    name,
                    nlu,
                    "repeated_non_text",
                    "high",
                    "I can't review attachments automatically, so I've asked a human teammate to help.",
                    state,
                )
            return self._reply(
                conversation,
                name,
                nlu,
                NON_TEXT_REPLY,
                sources=[],
            )

        if not text:
            return self._reply(conversation, name, nlu, NON_TEXT_REPLY)

        entities = merge_entities(
            list(nlu.entities or []), extract_rule_entities(text)
        )
        order_id = self._first_entity(entities, "ORDER_ID")
        intent = nlu.intent
        confidence = float(nlu.confidence)
        frustrated, frustration_terms = detect_frustration(text)

        # A customer answering the "share your order ID" prompt often sends only
        # the ID. Treat that as a valid order-status follow-up regardless of the
        # classifier's confidence on a bare token.
        if state.pending_slot == "order_id" and not order_id:
            order_id = find_order_id(text)
            if order_id:
                intent = "order_status"
                confidence = max(confidence, 0.95)

        if state.pending_slot == "order_id":
            if order_id:
                intent = "order_status"
                confidence = max(confidence, 0.95)
            elif (
                intent not in {"human_agent", "complaint", "goodbye"}
                and confidence < self.threshold
            ):
                state.pending_attempts += 1
                if state.pending_attempts >= self.max_attempts:
                    return self._handoff(
                        conversation,
                        name,
                        nlu,
                        "missing_order_id",
                        "normal",
                        "I still don't have a valid order ID. I've asked a human teammate to pick this up.",
                        state,
                    )
                return self._reply(
                    conversation,
                    name,
                    nlu,
                    "I need the order ID to look this up. It usually looks like ORD-1042 and is in your confirmation email.",
                )

        if intent == "human_agent":
            return self._handoff(
                conversation,
                name,
                nlu,
                "customer_requested_human",
                "high",
                "Of course — I'm connecting you with a human teammate now and pausing automatic replies.",
                state,
            )

        if intent == "complaint":
            return self._handoff(
                conversation,
                name,
                nlu,
                "complaint",
                "high",
                "I'm sorry about this. I've flagged your conversation for a human teammate and paused automatic replies.",
                state,
            )

        if frustrated:
            return self._handoff(
                conversation,
                name,
                nlu,
                "customer_frustrated",
                "high",
                "I'm sorry this has been frustrating. I've asked a human teammate to step in.",
                state,
                note=f"Frustration signals: {', '.join(frustration_terms[:5])}",
            )

        if confidence < self.threshold:
            return self._handoff(
                conversation,
                name,
                nlu,
                "low_confidence",
                "normal",
                "I want to make sure I get this right, so I'm bringing in a human teammate.",
                state,
            )

        if intent == "greeting":
            return self._reply(
                conversation,
                name,
                nlu,
                "How can I help today? I can check an order, explain returns, answer product questions, or connect you to a teammate.",
            )

        if intent == "goodbye":
            return self._reply(
                conversation,
                name,
                nlu,
                "You're welcome. I've marked this conversation resolved — message us anytime.",
                resolved=True,
            )

        if intent == "order_status":
            return self._handle_order_status(
                conversation, name, state, nlu, text, entities, order_id, db
            )

        if intent == "return_refund":
            return self._handle_return_refund(
                conversation, name, state, nlu, text, order_id, db
            )

        if intent == "product_info":
            return self._handle_knowledge(
                conversation, name, nlu, text, "product_info", state
            )

        if intent == "pricing":
            return self._handle_pricing(conversation, name, nlu, text, entities, state)

        # Explicit out-of-scope messages get one clarification before handoff.
        return self._handle_fallback(conversation, name, nlu, state)

    # ---------------------------------------------------------------- handlers
    def _handle_order_status(
        self,
        conversation,
        name: str | None,
        state: SessionState,
        nlu: NLUResult,
        text: str,
        entities: list[dict],
        order_id: str | None,
        db: Session | None,
    ) -> Decision:
        if not order_id and state.last_order_id and len(text.split()) <= 8:
            order_id = state.last_order_id
        if not order_id:
            state.pending_slot = "order_id"
            state.pending_attempts += 1
            if state.pending_attempts >= self.max_attempts:
                return self._handoff(
                    conversation,
                    name,
                    nlu,
                    "missing_order_id",
                    "normal",
                    "I can't look up the order without an ID. A human teammate can help from here.",
                    state,
                )
            return self._reply(
                conversation,
                name,
                nlu,
                "Please share your order ID (for example ORD-1042) and I'll check the verified status.",
            )

        lookup = self.orders_client.lookup(order_id)
        if db is not None:
            try:
                from app.models import OrderStatusEvent

                db.add(
                    OrderStatusEvent(
                        conversation_id=getattr(conversation, "id", None),
                        order_id=order_id,
                        found=lookup.found,
                        source=lookup.source,
                    )
                )
            except Exception:
                logger.exception("Could not record order lookup audit event")

        if lookup.error == "not_found":
            state.pending_slot = "order_id"
            state.pending_attempts += 1
            if state.pending_attempts >= self.max_attempts:
                return self._handoff(
                    conversation,
                    name,
                    nlu,
                    "order_not_found",
                    "normal",
                    f"I couldn't find {order_id}. I've asked a human teammate to check it.",
                    state,
                )
            return self._reply(conversation, name, nlu, lookup_error_answer(order_id))

        if not lookup.found or not lookup.order:
            return self._handoff(
                conversation,
                name,
                nlu,
                "orders_api_unavailable",
                "normal",
                orders_unavailable_answer(),
                state,
            )

        state.reset_pending()
        state.last_order_id = order_id
        return self._reply(
            conversation,
            name,
            nlu,
            order_status_answer(lookup.order),
            sources=[order_source(lookup.order)],
            entities=entities,
        )

    def _handle_return_refund(
        self,
        conversation,
        name: str | None,
        state: SessionState,
        nlu: NLUResult,
        text: str,
        order_id: str | None,
        db: Session | None,
    ) -> Decision:
        matches = self.faq_store.search(
            f"return refund policy {text}", top_k=3
        )
        policy_matches = [
            match
            for match in matches
            if {"return", "returns", "refund", "exchange"} & {str(t).lower() for t in match.get("tags", [])}
        ]
        if not policy_matches:
            return self._handoff(
                conversation,
                name,
                nlu,
                "knowledge_gap",
                "normal",
                "I don't have a verified answer for that return question, so I've asked a human teammate to help.",
                state,
            )

        lookup = None
        if order_id:
            result = self.orders_client.lookup(order_id)
            if result.error == "not_found":
                state.pending_slot = "order_id"
                state.pending_attempts += 1
                if state.pending_attempts >= self.max_attempts:
                    return self._handoff(
                        conversation,
                        name,
                        nlu,
                        "order_not_found",
                        "normal",
                        f"I couldn't find {order_id}. I've asked a human teammate to check it.",
                        state,
                    )
                return self._reply(
                    conversation,
                    name,
                    nlu,
                    f"{policy_matches[0]['answer']} I couldn't find {order_id}, so please check the ID and send it again.",
                    sources=knowledge_to_sources(policy_matches),
                )
            if result.error == "unavailable":
                return self._handoff(
                    conversation,
                    name,
                    nlu,
                    "orders_api_unavailable",
                    "normal",
                    orders_unavailable_answer(),
                    state,
                )
            lookup = result

        reply = return_policy_answer(policy_matches, lookup)
        sources = knowledge_to_sources(policy_matches)
        if lookup and lookup.found:
            sources.append(order_source(lookup.order or {}))
            state.reset_pending()
            # Refunds/returns are a money movement; a human must confirm the
            # eligibility and process it. The bot only states verified policy.
            return self._handoff(
                conversation,
                name,
                nlu,
                "return_refund_request",
                "high" if nlu.intent == "complaint" else "normal",
                reply,
                state,
                sources=sources,
            )

        state.pending_slot = "order_id"
        return self._reply(
            conversation,
            name,
            nlu,
            reply,
            sources=sources,
            entities=[{"type": "ORDER_ID", "value": order_id}] if order_id else [],
        )

    def _handle_knowledge(
        self,
        conversation,
        name: str | None,
        nlu: NLUResult,
        text: str,
        intent: str,
        state: SessionState,
    ) -> Decision:
        matches = self.faq_store.search(text, top_k=3)
        if not matches:
            return self._handoff(
                conversation,
                name,
                nlu,
                "knowledge_gap",
                "normal",
                "I don't have a verified answer for that yet, so I've asked a human teammate to help.",
                state,
            )
        answer = self._natural_reply(text, intent, matches[0]["answer"], knowledge_to_sources(matches))
        return self._reply(
            conversation,
            name,
            nlu,
            answer,
            sources=knowledge_to_sources(matches),
        )

    def _handle_pricing(
        self,
        conversation,
        name: str | None,
        nlu: NLUResult,
        text: str,
        entities: list[dict],
        state: SessionState,
    ) -> Decision:
        products = [
            str(entity.get("value"))
            for entity in entities
            if entity.get("type") == "PRODUCT" and entity.get("value")
        ]
        matches = self.faq_store.search(text, top_k=8)
        price_matches = [
            match
            for match in matches
            if is_pricing_chunk(match) and pricing_chunk_matches(match, text, products)
        ]
        if not price_matches:
            return self._handoff(
                conversation,
                name,
                nlu,
                "unverified_pricing",
                "normal",
                "I can't verify that price from a trusted source, so I won't guess. I've asked a human teammate to confirm it.",
                state,
            )
        answer = self._natural_reply(
            text, "pricing", price_matches[0]["answer"], knowledge_to_sources(price_matches)
        )
        return self._reply(
            conversation,
            name,
            nlu,
            answer,
            sources=knowledge_to_sources(price_matches),
        )

    def _handle_fallback(
        self, conversation, name: str | None, nlu: NLUResult, state: SessionState
    ) -> Decision:
        state.fallback_count += 1
        if state.fallback_count >= self.max_fallbacks:
            return self._handoff(
                conversation,
                name,
                nlu,
                "out_of_scope",
                "normal",
                "I'm still not sure I can help with that safely. I've asked a human teammate to take over.",
                state,
            )
        return self._reply(conversation, name, nlu, CLARIFY_REPLY)

    # ----------------------------------------------------------------- helpers
    def _natural_reply(
        self, text: str, intent: str, grounded: str, sources: list[dict]
    ) -> str:
        if not sources:
            return grounded
        try:
            rewritten = self.llm.rewrite(
                GroundedContext(
                    customer_message=text,
                    intent=intent,
                    grounded_answer=grounded,
                    sources=sources,
                )
            )
            return rewritten.strip() or grounded
        except Exception:
            logger.exception("LLM rewrite failed; using grounded answer")
            return grounded

    @staticmethod
    def _first_entity(entities: list[dict], entity_type: str) -> str | None:
        for entity in entities:
            if entity.get("type") == entity_type and entity.get("value"):
                return str(entity["value"])
        return None

    def _compose(self, conversation, name: str | None, text: str) -> str:
        if getattr(conversation, "bot_identified", False):
            return text
        if "automated" in text.lower():
            return text
        return f"{bot_disclosure_prefix(name)} {text}"

    def _reply(
        self,
        conversation,
        name: str | None,
        nlu: NLUResult,
        text: str,
        *,
        sources: list[dict] | None = None,
        entities: list[dict] | None = None,
        resolved: bool = False,
    ) -> Decision:
        return Decision(
            reply=self._compose(conversation, name, text),
            intent=nlu.intent,
            confidence=nlu.confidence,
            entities=entities if entities is not None else list(nlu.entities),
            top_intents=list(nlu.top_intents),
            sources=sources or [],
            resolved=resolved,
            model_version=nlu.model_version,
            source=nlu.source,
        )

    def _handoff(
        self,
        conversation,
        name: str | None,
        nlu: NLUResult,
        reason: str,
        priority: str,
        text: str,
        state: SessionState,
        *,
        note: str | None = None,
        sources: list[dict] | None = None,
    ) -> Decision:
        state.reset_pending()
        return Decision(
            reply=self._compose(conversation, name, text),
            intent=nlu.intent,
            confidence=nlu.confidence,
            entities=list(nlu.entities),
            top_intents=list(nlu.top_intents),
            sources=sources or [],
            handoff=True,
            handoff_reason=reason,
            priority=priority,
            model_version=nlu.model_version,
            source=nlu.source,
        )
