from __future__ import annotations

import re


def normalize_order_id(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if not cleaned:
        return raw.strip().upper()
    if cleaned.isdigit():
        return f"ORD-{cleaned}"
    if cleaned.startswith("ORD") and cleaned[3:].isdigit():
        return f"ORD-{cleaned[3:]}"
    return cleaned
