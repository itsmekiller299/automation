from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.config import settings
from app.services.orders import OrderLookup


@dataclass(slots=True)
class KnowledgeAnswer:
    answer: str
    sources: list[dict] = field(default_factory=list)
    grounded: bool = True


def _format_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        return value


def order_status_answer(order: dict) -> str:
    order_id = order.get("order_id", "your order")
    status = order.get("status_label") or order.get("status") or "in progress"
    parts = [f"{order_id} is currently: {status}."]
    item = order.get("item")
    if item:
        parts.append(f"Item: {item}.")
    eta = _format_date(order.get("eta"))
    if eta and order.get("status") not in {"delivered", "cancelled"}:
        parts.append(f"Estimated delivery: {eta}.")
    delivered = _format_date(order.get("delivered_at"))
    if delivered:
        parts.append(f"Delivered on {delivered}.")
    tracking = order.get("tracking_url")
    if tracking:
        parts.append(f"Tracking: {tracking}")
    return " ".join(parts)


def order_source(order: dict) -> dict:
    return {
        "id": f"order:{order.get('order_id')}",
        "question": "Order status",
        "source": "orders_api",
        "score": 1.0,
    }


def find_price_fact(answer: str) -> bool:
    return bool(re.search(r"(?:[$₹€£]\s?\d|\b\d+\s?(?:usd|inr|eur|gbp)\b)", answer, re.I))


def is_pricing_chunk(chunk: dict) -> bool:
    tags = {str(tag).lower() for tag in chunk.get("tags") or []}
    chunk_id = str(chunk.get("id") or "").lower()
    return (
        "price" in tags
        or "pricing" in tags
        or "price" in chunk_id
        or "discount" in tags
        or find_price_fact(chunk.get("answer", ""))
    )


_GENERIC_PRICING_TERMS = {
    "price", "pricing", "cost", "costs", "much", "how", "rate", "discount",
    "offer", "sale", "cheap", "cheapest", "best", "value", "money", "pay",
    "kitna", "kitne", "ka", "ki", "kya", "daam", "kimat", "sasta", "paise",
    "please", "tell", "what", "whats", "for", "the", "and", "does", "do",
}


def pricing_chunk_matches(chunk: dict, query: str, products: list[str]) -> bool:
    """Verify a price chunk is actually about the product being asked about.

    Lexical retrieval often ranks a different product's price page because both
    contain the words "price" and "cost". The bot must not answer the wrong
    price, so require a product match (or meaningful query-term overlap when no
    product was extracted) before using the chunk.
    """
    haystack = " ".join(
        [
            str(chunk.get("question") or ""),
            str(chunk.get("answer") or ""),
            " ".join(str(tag) for tag in chunk.get("tags") or []),
        ]
    ).lower()

    if products:
        for product in products:
            normalized = product.lower().strip()
            if normalized and normalized in haystack:
                return True
            first_word = normalized.split()[0] if normalized else ""
            if first_word and len(first_word) >= 4 and re.search(
                rf"(?<!\w){re.escape(first_word)}(?!\w)", haystack
            ):
                return True
        return False

    query_terms = {
        token
        for token in re.findall(r"[a-z0-9]+", query.lower())
        if len(token) > 2 and token not in _GENERIC_PRICING_TERMS
    }
    if not query_terms:
        # A generic "what are your prices/discounts?" question may use a
        # policy chunk that is explicitly tagged for pricing.
        return bool({"price", "pricing", "discount"} & {str(t).lower() for t in chunk.get("tags") or []})
    haystack_terms = set(re.findall(r"[a-z0-9]+", haystack))
    return bool(query_terms & haystack_terms)


def knowledge_to_sources(matches: list[dict]) -> list[dict]:
    return [
        {
            "id": match.get("id"),
            "question": match.get("question"),
            "source": match.get("source"),
            "score": match.get("score"),
            "backend": match.get("backend"),
        }
        for match in matches
    ]


def lookup_error_answer(order_id: str) -> str:
    return (
        f"I couldn't find order {order_id} in our verified order system. "
        "Please check the ID and send it again, or ask for a human teammate."
    )


def orders_unavailable_answer() -> str:
    return (
        "I can't reach the order system safely right now. I've flagged this for a human "
        "teammate so they can check it without guessing."
    )


def return_policy_answer(matches: list[dict], order: OrderLookup | None = None) -> str:
    policy = matches[0]["answer"] if matches else ""
    if order and order.found and order.order:
        eligible = bool(order.order.get("refund_eligible"))
        order_id = order.order.get("order_id")
        if eligible:
            detail = (
                f"Order {order_id} is within the return window and is eligible for review. "
                "I can't approve or issue a refund myself, so I've passed this to a teammate."
            )
        else:
            detail = (
                f"Order {order_id} is outside the standard return window or is not returnable. "
                "A teammate can review any exception with you."
            )
        return f"{policy} {detail}".strip()
    return (
        f"{policy} Please share your order ID so a teammate can check the specific order. "
        "I won't promise a refund until it has been reviewed."
    ).strip()


def bot_disclosure_prefix(customer_name: str | None = None) -> str:
    first_name = (customer_name or "").strip().split(" ")[0]
    greeting = f"Hi {first_name}, " if first_name else ""
    return f"{greeting}I'm the automated assistant for {settings.brand_name}."
