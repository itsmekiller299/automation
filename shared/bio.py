"""BIO alignment and decoding used by both training and inference."""

from __future__ import annotations

from collections.abc import Iterable

from shared.entities import normalize_order_id
from shared.labels import ID2ENTITY

IGNORE_INDEX = -100


def align_entity_labels(
    offset_mapping: list[tuple[int, int]],
    entities: Iterable[dict],
    label2id: dict[str, int],
) -> list[int]:
    """Map character-span entities onto token labels.

    Special tokens (offset 0,0) get -100 so they are ignored by the loss. A
    multi-token entity receives B- on its first overlapping token and I- on the
    rest, which is required for a token-classification head.
    """
    labels = [label2id["O"]] * len(offset_mapping)
    for index, (start, end) in enumerate(offset_mapping):
        if start == end:
            labels[index] = IGNORE_INDEX

    for entity in entities:
        entity_type = str(entity.get("type") or "")
        if entity_type not in {"ORDER_ID", "PRODUCT", "DATE"}:
            continue
        start = int(entity.get("start", 0))
        end = int(entity.get("end", 0))
        if end <= start:
            continue
        overlapping = [
            index
            for index, (token_start, token_end) in enumerate(offset_mapping)
            if token_start != token_end and token_start < end and token_end > start
        ]
        if not overlapping:
            continue
        labels[overlapping[0]] = label2id[f"B-{entity_type}"]
        for index in overlapping[1:]:
            labels[index] = label2id[f"I-{entity_type}"]
    return labels


def decode_bio(
    text: str,
    offset_mapping: list[tuple[int, int]],
    tag_ids: list[int],
    word_ids: list[int | None] | None = None,
) -> list[dict]:
    """Decode predicted BIO tags into character-span entities."""
    entities: list[dict] = []
    current_type: str | None = None
    current_start = 0
    current_end = 0

    def flush() -> None:
        nonlocal current_type, current_start, current_end
        if current_type and current_end > current_start:
            raw = text[current_start:current_end].strip()
            if raw:
                value = normalize_order_id(raw) if current_type == "ORDER_ID" else raw
                entities.append(
                    {
                        "type": current_type,
                        "value": value,
                        "start": current_start,
                        "end": current_end,
                        "score": 0.9,
                    }
                )
        current_type = None
        current_start = 0
        current_end = 0

    previous_word: int | None = -1
    for index, tag_id in enumerate(tag_ids):
        tag = ID2ENTITY.get(int(tag_id), "O")
        start, end = offset_mapping[index] if index < len(offset_mapping) else (0, 0)
        if start == end:
            continue
        if word_ids is not None:
            word_id = word_ids[index]
            if word_id is None:
                flush()
                previous_word = None
                continue
            if word_id == previous_word:
                if current_type and end > current_end:
                    current_end = end
                continue
            previous_word = word_id

        if tag == "O":
            flush()
            continue
        prefix, _, entity_type = tag.partition("-")
        if prefix == "B" or entity_type != current_type:
            flush()
            current_type = entity_type
            current_start = start
            current_end = end
        else:
            current_end = max(current_end, end)
    flush()
    return entities
