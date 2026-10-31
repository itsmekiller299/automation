from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path

from app.nlu.entities import extract_rule_entities, merge_entities
from app.nlu.types import NLUResult
from shared.bio import decode_bio
from shared.labels import ID2ENTITY, ID2INTENT, INTENTS

logger = logging.getLogger(__name__)


def _softmax(values: list[float]) -> list[float]:
    if not values:
        return []
    peak = max(values)
    exps = [math.exp(value - peak) for value in values]
    total = sum(exps) or 1.0
    return [value / total for value in exps]


class TransformerNLU:
    def __init__(
        self,
        model_dir: Path,
        onnx_path: Path,
        temperature: float | None = None,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.onnx_path = Path(onnx_path)
        self.temperature = temperature or 1.0
        self.mode: str = ""
        self.model_version = "transformer"
        self._session = None
        self._model = None
        self._tokenizer = None
        self._torch = None
        self._config: dict = {}
        self._load()

    def _load(self) -> None:
        config_path = self.model_dir / "model_config.json"
        if config_path.exists():
            try:
                self._config = json.loads(config_path.read_text())
            except json.JSONDecodeError:
                self._config = {}
        self.model_version = str(self._config.get("version") or "transformer")

        calibration_path = self.model_dir / "calibration.json"
        if calibration_path.exists():
            try:
                calibration = json.loads(calibration_path.read_text())
                self.temperature = float(calibration.get("temperature", self.temperature))
                self.model_version = str(calibration.get("version", self.model_version))
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.warning("Could not read calibration.json; using T=1.0")

        from transformers import AutoTokenizer

        if not self.model_dir.exists():
            raise FileNotFoundError(f"NLU model directory not found: {self.model_dir}")

        self._tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir), local_files_only=True)

        if self.onnx_path.exists():
            import onnxruntime as ort

            self._session = ort.InferenceSession(
                str(self.onnx_path), providers=["CPUExecutionProvider"]
            )
            self.mode = "onnx"
            logger.info("NLU loaded ONNX model from %s", self.onnx_path)
            return

        checkpoint = self.model_dir / "pytorch_model.pt"
        if not checkpoint.exists():
            raise FileNotFoundError(
                f"No model.onnx or pytorch_model.pt in {self.model_dir}. Run training/export first."
            )

        import torch

        from shared.intent_model import IntentEntityModel

        self._torch = torch
        bundle = torch.load(str(checkpoint), map_location="cpu", weights_only=False)
        encoder_name = bundle.get("encoder_name") or self._config.get("encoder_name")
        state_dict = bundle.get("state_dict") or bundle
        model = IntentEntityModel(
            encoder_name=encoder_name,
            num_intents=len(INTENTS),
            num_entity_labels=len(ID2ENTITY),
        )
        model.load_state_dict(state_dict)
        model.eval()
        self._model = model
        self.mode = "torch"
        logger.info("NLU loaded Torch checkpoint from %s", checkpoint)

    def _prepare(self, text: str) -> dict:
        encoded = self._tokenizer(
            text,
            return_tensors="np",
            truncation=True,
            max_length=128,
            return_offsets_mapping=True,
        )
        return {
            "input_ids": encoded["input_ids"],
            "attention_mask": encoded["attention_mask"],
            "offset_mapping": encoded["offset_mapping"][0].tolist(),
            "word_ids": encoded.word_ids(0),
        }

    def _predict_onnx(self, text: str) -> tuple[list[float], list[int], dict]:
        prepared = self._prepare(text)
        feed = {
            "input_ids": prepared["input_ids"].astype("int64"),
            "attention_mask": prepared["attention_mask"].astype("int64"),
        }
        available = {item.name for item in self._session.get_inputs()}
        feed = {key: value for key, value in feed.items() if key in available}
        outputs = self._session.run(None, feed)
        intent_logits = None
        entity_tags = None
        for output in outputs:
            shape = getattr(output, "shape", [])
            if len(shape) == 2:
                intent_logits = output[0].tolist()
            elif len(shape) == 3:
                entity_tags = output[0].argmax(axis=-1).tolist()
        if intent_logits is None or entity_tags is None:
            raise RuntimeError("Unexpected ONNX output shapes")
        return intent_logits, entity_tags, prepared

    def _predict_torch(self, text: str) -> tuple[list[float], list[int], dict]:
        torch = self._torch
        prepared = self._prepare(text)
        with torch.no_grad():
            input_ids = torch.tensor(prepared["input_ids"], dtype=torch.long)
            attention_mask = torch.tensor(prepared["attention_mask"], dtype=torch.long)
            intent_logits, entity_logits = self._model(input_ids, attention_mask)
        return (
            intent_logits[0].tolist(),
            entity_logits[0].argmax(dim=-1).tolist(),
            prepared,
        )

    def predict(self, text: str) -> NLUResult:
        started = time.perf_counter()
        intent_logits, entity_tags, prepared = (
            self._predict_onnx(text) if self.mode == "onnx" else self._predict_torch(text)
        )

        scaled = [value / max(self.temperature, 0.05) for value in intent_logits]
        probabilities = _softmax(scaled)
        ranked = sorted(
            enumerate(probabilities), key=lambda item: item[1], reverse=True
        )[:3]
        top_intents = [
            {
                "intent": ID2INTENT[int(index)],
                "confidence": round(float(probability), 4),
            }
            for index, probability in ranked
        ]
        best_index, best_probability = ranked[0]
        model_entities = decode_bio(
            text,
            prepared["offset_mapping"],
            entity_tags,
            prepared["word_ids"],
        )
        # Regex entities are merged in so order IDs found in text are never lost
        # to a tokenization edge case. Model spans win on overlap.
        entities = merge_entities(model_entities, extract_rule_entities(text))

        return NLUResult(
            intent=ID2INTENT[int(best_index)],
            confidence=round(float(best_probability), 4),
            entities=entities,
            top_intents=top_intents,
            model_version=self.model_version,
            calibrated=abs(self.temperature - 1.0) > 1e-6,
            source="transformer",
            latency_ms=(time.perf_counter() - started) * 1000,
        )
