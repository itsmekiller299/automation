"""Multi-task transformer for intent classification + BIO entity tagging.

This module is imported by the training pipeline and, when a local checkpoint
exists, by the inference service. Keeping the architecture in one place means
the Torch checkpoint and ONNX graph are built from exactly the same code.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from transformers import AutoModel

from shared.labels import ENTITY_LABELS, INTENTS


class IntentEntityModel(nn.Module):
    def __init__(
        self,
        encoder_name: str = "distilbert-base-uncased",
        num_intents: int = len(INTENTS),
        num_entity_labels: int = len(ENTITY_LABELS),
        dropout: float = 0.15,
    ) -> None:
        super().__init__()
        self.encoder = AutoModel.from_pretrained(encoder_name)
        self.encoder_name = encoder_name
        self.num_intents = num_intents
        self.num_entity_labels = num_entity_labels
        hidden = self.encoder.config.hidden_size
        self.dropout = nn.Dropout(dropout)
        self.intent_head = nn.Linear(hidden, num_intents)
        self.entity_head = nn.Linear(hidden, num_entity_labels)
        self._init_heads(hidden)

    def _init_heads(self, hidden: int) -> None:
        for head in (self.intent_head, self.entity_head):
            nn.init.normal_(head.weight, std=0.02)
            nn.init.zeros_(head.bias)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        token_type_ids: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        encoder_kwargs = {"input_ids": input_ids, "attention_mask": attention_mask}
        if token_type_ids is not None:
            encoder_kwargs["token_type_ids"] = token_type_ids

        outputs = self.encoder(**encoder_kwargs)
        sequence = outputs.last_hidden_state
        pooled = sequence[:, 0]
        intent_logits = self.intent_head(self.dropout(pooled))
        entity_logits = self.entity_head(self.dropout(sequence))
        return intent_logits, entity_logits
