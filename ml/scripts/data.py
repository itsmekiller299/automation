from __future__ import annotations

import json
from pathlib import Path

import torch
from torch.utils.data import Dataset
from transformers import PreTrainedTokenizerBase

from shared.bio import align_entity_labels
from shared.labels import ENTITY2ID, INTENT2ID, INTENTS


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed JSON on line {line_no} of {path}: {exc}") from exc
            if record.get("intent") not in INTENTS:
                continue
            records.append(record)
    return records


class IntentDataset(Dataset):
    def __init__(
        self,
        records: list[dict],
        tokenizer: PreTrainedTokenizerBase,
        max_length: int = 128,
    ) -> None:
        self.examples: list[dict] = []
        for record in records:
            encoded = tokenizer(
                record["text"],
                truncation=True,
                max_length=max_length,
                padding=False,
                return_offsets_mapping=True,
            )
            offsets = [tuple(pair) for pair in encoded["offset_mapping"]]
            word_ids = encoded.word_ids(0) if hasattr(encoded, "word_ids") else None
            labels = align_entity_labels(offsets, record.get("entities") or [], ENTITY2ID)
            self.examples.append(
                {
                    "input_ids": list(encoded["input_ids"]),
                    "attention_mask": list(encoded["attention_mask"]),
                    "intent": INTENT2ID[record["intent"]],
                    "entity_labels": labels,
                    "offsets": offsets,
                    "word_ids": [-1 if word is None else word for word in (word_ids or [])],
                    "text": record["text"],
                    "gold_entities": record.get("entities") or [],
                }
            )

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict:
        return self.examples[index]


def collate_batch(batch: list[dict], pad_token_id: int) -> dict[str, torch.Tensor | list]:
    max_length = max(len(item["input_ids"]) for item in batch)
    input_ids: list[list[int]] = []
    attention_mask: list[list[int]] = []
    entity_labels: list[list[int]] = []
    offsets: list[list[tuple[int, int]]] = []
    word_ids: list[list[int]] = []
    texts: list[str] = []
    gold_entities: list[list[dict]] = []

    for item in batch:
        pad = max_length - len(item["input_ids"])
        input_ids.append(item["input_ids"] + [pad_token_id] * pad)
        attention_mask.append(item["attention_mask"] + [0] * pad)
        entity_labels.append(item["entity_labels"] + [-100] * pad)
        offsets.append(item["offsets"] + [(0, 0)] * pad)
        word_ids.append(item["word_ids"] + [-1] * pad)
        texts.append(item["text"])
        gold_entities.append(item["gold_entities"])

    return {
        "input_ids": torch.tensor(input_ids, dtype=torch.long),
        "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
        "entity_labels": torch.tensor(entity_labels, dtype=torch.long),
        "intent_labels": torch.tensor([item["intent"] for item in batch], dtype=torch.long),
        "offsets": offsets,
        "word_ids": word_ids,
        "texts": texts,
        "gold_entities": gold_entities,
    }
