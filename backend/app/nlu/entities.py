from __future__ import annotations

import re

from shared.catalog import PRODUCTS
from shared.entities import normalize_order_id
from shared.labels import ENTITY_LABELS

ORDER_RE = re.compile(
    r"\b(?:(?:ord|order)(?:\s+(?:id|number|no\.?))?\s*[-\s#:]*|#)\s*([A-Za-z]{0,3}\d{3,10})\b",
    re.IGNORECASE,
)
ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b")
MONTH_DATE_RE = re.compile(
    r"\b(?:\d{1,2}\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)|"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2})\b",
    re.IGNORECASE,
)
RELATIVE_DATE_RE = re.compile(
    r"\b(?:today|tomorrow|tonight|next week|next month|this weekend|"
    r"next (?:mon|tues|wednes|thurs|fri|satur|sun)day|"
    r"aaj|kal|parso|agle hafte)\b",
    re.IGNORECASE,
)
PHONE_OR_LONG_NUMBER_RE = re.compile(r"^\+?\d{10,15}$")

_DATE_WORDS = RELATIVE_DATE_RE


def find_order_id(text: str) -> str | None:
    match = ORDER_RE.search(text)
    if match:
        return normalize_order_id(match.group(1))
    # Also accept a bare order-style token such as ORD-1042 or #1042.
    bare = re.search(r"\b(ORD[-\s]?\d{3,10})\b", text, re.IGNORECASE)
    if bare:
        return normalize_order_id(bare.group(1))
    return None


def _add_entity(
    entities: list[dict], occupied: list[tuple[int, int]], entity_type: str, value: str, start: int, end: int
) -> None:
    if start >= end:
        return
    for left, right in occupied:
        if start < right and end > left:
            return
    occupied.append((start, end))
    entities.append(
        {"type": entity_type, "value": value, "start": start, "end": end, "score": 1.0}
    )


def extract_rule_entities(text: str) -> list[dict]:
    """Regex + catalog entity extraction used by the rules fallback.

    It also runs after transformer inference as a safety net: deterministic
    order IDs are too important to leave to a small model.
    """
    entities: list[dict] = []
    occupied: list[tuple[int, int]] = []

    for match in ORDER_RE.finditer(text):
        digits = match.group(1)
        if PHONE_OR_LONG_NUMBER_RE.match(digits) and len(re.findall(r"\d", digits)) > 10:
            continue
        _add_entity(
            entities,
            occupied,
            "ORDER_ID",
            normalize_order_id(digits),
            match.start(),
            match.end(),
        )

    # Match longest product aliases first so "nimbus chair" wins over "nimbus".
    aliases: list[tuple[str, str]] = []
    for product in PRODUCTS:
        for alias in {product["name"], *product.get("aliases", [])}:
            aliases.append((alias, product["name"]))
    for alias, canonical in sorted(aliases, key=lambda item: len(item[0]), reverse=True):
        pattern = re.compile(rf"\b{re.escape(alias)}\b", re.IGNORECASE)
        for match in pattern.finditer(text):
            _add_entity(
                entities, occupied, "PRODUCT", canonical, match.start(), match.end()
            )

    for regex in (_DATE_WORDS, ISO_DATE_RE, MONTH_DATE_RE):
        for match in regex.finditer(text):
            _add_entity(entities, occupied, "DATE", match.group(0), match.start(), match.end())

    entities.sort(key=lambda item: item["start"])
    return entities


def merge_entities(primary: list[dict], secondary: list[dict]) -> list[dict]:
    """Union entities, preferring primary spans and dropping overlaps."""
    merged: list[dict] = []
    occupied: list[tuple[int, int]] = []
    for entity in [*primary, *secondary]:
        start = int(entity.get("start", 0))
        end = int(entity.get("end", 0))
        value = str(entity.get("value", ""))
        if not value:
            continue
        if start >= end:
            # Model may only return a value/type pair; keep it as a value-only entity.
            merged.append(entity)
            continue
        overlap = any(start < right and end > left for left, right in occupied)
        if overlap:
            continue
        occupied.append((start, end))
        merged.append(entity)
    merged.sort(key=lambda item: int(item.get("start", 0)))
    return merged


def bio_labels_for_span(entity_type: str) -> tuple[str, str]:
    if entity_type not in {"ORDER_ID", "PRODUCT", "DATE"}:
        raise ValueError(f"Unknown entity type {entity_type}")
    if f"B-{entity_type}" not in ENTITY_LABELS:
        raise ValueError(entity_type)
    return f"B-{entity_type}", f"I-{entity_type}"
