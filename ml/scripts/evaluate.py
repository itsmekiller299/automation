#!/usr/bin/env python3
"""Evaluate the trained NLU model and write an auditable report.

Outputs:
  evaluation.json      machine-readable metrics (intent, entities, calibration)
  report.md            human-readable summary with per-intent table
  confusion_matrix.png intent confusion matrix

Use --fail-under 0.90 to make CI fail when macro-F1 drops below the target.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch.utils.data import DataLoader  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

from ml.scripts.data import IntentDataset, collate_batch, load_jsonl  # noqa: E402
from ml.scripts.metrics import (  # noqa: E402
    classification_metrics,
    entity_metrics,
    expected_calibration_error,
    negative_log_likelihood,
    save_confusion_matrix,
    softmax,
)
from shared.bio import decode_bio  # noqa: E402
from shared.intent_model import IntentEntityModel  # noqa: E402
from shared.labels import ID2ENTITY, INTENTS  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-dir", type=Path, default=PROJECT_ROOT / "ml/artifacts/intent-model"
    )
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "ml/data/splits")
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "ml/artifacts/evaluation"
    )
    parser.add_argument("--split", choices=["train", "val", "test"], default="test")
    parser.add_argument("--backend", choices=["auto", "torch", "onnx"], default="auto")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-length", type=int, default=0)
    parser.add_argument("--confidence-threshold", type=float, default=0.80)
    parser.add_argument(
        "--fail-under",
        type=float,
        default=0.0,
        help="Exit non-zero when macro-F1 is below this value (0 disables).",
    )
    return parser.parse_args()


def load_metadata(model_dir: Path) -> tuple[dict, dict]:
    config: dict = {}
    config_path = model_dir / "model_config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
    calibration: dict = {"temperature": 1.0}
    calibration_path = model_dir / "calibration.json"
    if calibration_path.exists():
        calibration = json.loads(calibration_path.read_text())
    return config, calibration


def choose_backend(requested: str, model_dir: Path) -> str:
    onnx_exists = (model_dir / "model.onnx").exists()
    checkpoint_exists = (model_dir / "pytorch_model.pt").exists()
    if requested == "onnx" and not onnx_exists:
        raise SystemExit(f"No model.onnx in {model_dir}; run export_onnx.py first.")
    if requested == "torch" and not checkpoint_exists:
        raise SystemExit(f"No pytorch_model.pt in {model_dir}; run train_intent.py first.")
    if requested == "auto":
        if onnx_exists:
            return "onnx"
        if checkpoint_exists:
            return "torch"
        raise SystemExit(f"No model.onnx or pytorch_model.pt in {model_dir}.")
    return requested


class TorchPredictor:
    def __init__(self, model_dir: Path, config: dict, device: str = "cpu") -> None:
        self.device = torch.device(device)
        bundle = torch.load(
            str(model_dir / "pytorch_model.pt"), map_location="cpu", weights_only=False
        )
        self.model = IntentEntityModel(
            encoder_name=bundle.get("encoder_name") or config.get("encoder_name"),
            num_intents=len(INTENTS),
            num_entity_labels=len(ID2ENTITY),
        )
        self.model.load_state_dict(bundle["state_dict"])
        self.model.to(self.device)
        self.model.eval()

    def predict(self, batch: dict) -> tuple[np.ndarray, list[list[int]]]:
        with torch.no_grad():
            intent_logits, entity_logits = self.model(
                batch["input_ids"].to(self.device),
                batch["attention_mask"].to(self.device),
            )
        return (
            intent_logits.detach().cpu().numpy(),
            entity_logits.argmax(dim=-1).detach().cpu().tolist(),
        )


class OnnxPredictor:
    def __init__(self, model_path: Path) -> None:
        import onnxruntime as ort

        self.session = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        self.input_names = {item.name for item in self.session.get_inputs()}

    def predict(self, batch: dict) -> tuple[np.ndarray, list[list[int]]]:
        feed = {
            "input_ids": batch["input_ids"].numpy().astype("int64"),
            "attention_mask": batch["attention_mask"].numpy().astype("int64"),
        }
        feed = {key: value for key, value in feed.items() if key in self.input_names}
        outputs = self.session.run(None, feed)
        intent_logits = None
        entity_tags = None
        for output in outputs:
            if output.ndim == 2:
                intent_logits = output
            elif output.ndim == 3:
                entity_tags = output.argmax(axis=-1).tolist()
        if intent_logits is None or entity_tags is None:
            raise RuntimeError("Unexpected ONNX output shapes")
        return intent_logits, entity_tags


def evaluate(args: argparse.Namespace) -> dict:
    config, calibration = load_metadata(args.model_dir)
    temperature = float(calibration.get("temperature", 1.0))
    max_length = args.max_length or int(config.get("max_length", 128))
    backend = choose_backend(args.backend, args.model_dir)

    records = load_jsonl(args.data_dir / f"{args.split}.jsonl")
    if not records:
        raise SystemExit(f"No records in {args.data_dir / (args.split + '.jsonl')}")

    tokenizer = AutoTokenizer.from_pretrained(
        str(args.model_dir), local_files_only=True
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token or tokenizer.cls_token
    dataset = IntentDataset(records, tokenizer, max_length=max_length)
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=partial(collate_batch, pad_token_id=tokenizer.pad_token_id),
        num_workers=0,
    )

    predictor = (
        OnnxPredictor(args.model_dir / "model.onnx")
        if backend == "onnx"
        else TorchPredictor(args.model_dir, config)
    )

    all_logits: list[np.ndarray] = []
    labels: list[int] = []
    gold_entities: list[list[dict]] = []
    predicted_entities: list[list[dict]] = []
    texts: list[str] = []

    for batch in loader:
        intent_logits, entity_tags = predictor.predict(batch)
        all_logits.append(np.asarray(intent_logits))
        labels.extend(batch["intent_labels"].tolist())
        texts.extend(batch["texts"])
        for index, text in enumerate(batch["texts"]):
            tags = entity_tags[index]
            offsets = [tuple(pair) for pair in batch["offsets"][index][: len(tags)]]
            word_ids = [
                None if word == -1 else word
                for word in batch["word_ids"][index][: len(tags)]
            ]
            decoded = decode_bio(text, offsets, tags, word_ids)
            predicted_entities.append(
                [
                    {
                        "type": item["type"],
                        "start": item["start"],
                        "end": item["end"],
                        "value": item["value"],
                    }
                    for item in decoded
                ]
            )
            gold_entities.append(batch["gold_entities"][index])

    logits = np.concatenate(all_logits, axis=0)
    labels_array = np.asarray(labels, dtype=np.int64)
    probabilities = softmax(logits, temperature)
    predictions = probabilities.argmax(axis=1).tolist()

    intent_metrics = classification_metrics(labels, predictions)
    entity_scores = entity_metrics(gold_entities, predicted_entities)
    ece = expected_calibration_error(probabilities, labels_array)
    nll = negative_log_likelihood(probabilities, labels_array)
    uncalibrated = expected_calibration_error(softmax(logits, 1.0), labels_array)

    confidences = probabilities.max(axis=1)
    correct = np.asarray(predictions) == labels_array
    low_confidence = confidences < args.confidence_threshold
    handoff_simulation = {
        "threshold": args.confidence_threshold,
        "handoff_rate": round(float(low_confidence.mean()), 4),
        "accuracy_above_threshold": round(
            float(correct[~low_confidence].mean()) if (~low_confidence).any() else 0.0,
            4,
        ),
        "accuracy_below_threshold": round(
            float(correct[low_confidence].mean()) if low_confidence.any() else 0.0,
            4,
        ),
        "high_confidence_support": int((~low_confidence).sum()),
        "low_confidence_support": int(low_confidence.sum()),
    }

    confusion_pairs = []
    for actual, predicted in zip(labels, predictions, strict=False):
        if actual != predicted:
            confusion_pairs.append((INTENTS[actual], INTENTS[predicted]))
    from collections import Counter

    common_confusions = [
        {"actual": actual, "predicted": predicted, "count": count}
        for (actual, predicted), count in Counter(confusion_pairs).most_common(8)
    ]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    plot_written = save_confusion_matrix(
        intent_metrics["confusion_matrix"], args.output_dir / "confusion_matrix.png"
    )

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_dir": str(args.model_dir),
        "model_version": config.get("version", "unknown"),
        "backend": backend,
        "split": args.split,
        "records": len(records),
        "temperature": temperature,
        "calibration": {
            "ece_uncalibrated": round(uncalibrated, 6),
            "ece_calibrated": round(ece, 6),
            "nll_calibrated": round(nll, 6),
        },
        "intent": intent_metrics,
        "entities": entity_scores,
        "handoff_simulation": handoff_simulation,
        "common_confusions": common_confusions,
        "confusion_matrix_png": plot_written,
        "target": {"macro_f1": 0.90, "met": intent_metrics["macro_f1"] >= 0.90},
        "data_note": (
            "Templated seed data shares phrasing between splits, so these numbers "
            "are optimistic. Re-run on held-out, anonymised production utterances."
        ),
    }
    return result


def render_report(result: dict) -> str:
    intent = result["intent"]
    lines = [
        "# NLU evaluation report",
        "",
        f"- Model version: `{result['model_version']}`",
        f"- Backend: `{result['backend']}`",
        f"- Split: `{result['split']}` ({result['records']} examples)",
        f"- Temperature: `{result['temperature']}`",
        f"- Macro-F1: **{intent['macro_f1']:.4f}** (target 0.90: "
        f"{'met' if result['target']['met'] else 'not met'})",
        f"- Accuracy: **{intent['accuracy']:.4f}**",
        f"- Weighted F1: {intent['weighted_f1']:.4f}",
        "",
        "## Calibration",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| ECE before temperature scaling | {result['calibration']['ece_uncalibrated']:.4f} |",
        f"| ECE after temperature scaling | {result['calibration']['ece_calibrated']:.4f} |",
        f"| NLL after temperature scaling | {result['calibration']['nll_calibrated']:.4f} |",
        "",
        "## Per-intent metrics",
        "",
        "| Intent | Precision | Recall | F1 | Support |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, row in intent["per_intent"].items():
        lines.append(
            f"| {name} | {row['precision']:.3f} | {row['recall']:.3f} | "
            f"{row['f1']:.3f} | {row['support']} |"
        )

    entities = result["entities"]
    lines += [
        "",
        "## Entity extraction (exact span)",
        "",
        f"- Overall: P={entities['precision']:.3f}, R={entities['recall']:.3f}, "
        f"F1={entities['f1']:.3f}",
        "",
        "| Entity | Precision | Recall | F1 | Support |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, row in entities["per_type"].items():
        lines.append(
            f"| {name} | {row['precision']:.3f} | {row['recall']:.3f} | "
            f"{row['f1']:.3f} | {row['support']} |"
        )

    handoff = result["handoff_simulation"]
    lines += [
        "",
        "## Handoff simulation",
        "",
        f"- Confidence threshold: {handoff['threshold']}",
        f"- Would hand off: {handoff['handoff_rate'] * 100:.1f}% of messages",
        f"- Accuracy above threshold: {handoff['accuracy_above_threshold']:.3f} "
        f"({handoff['high_confidence_support']} messages)",
        f"- Accuracy below threshold: {handoff['accuracy_below_threshold']:.3f} "
        f"({handoff['low_confidence_support']} messages)",
    ]

    if result["common_confusions"]:
        lines += ["", "## Most common confusions", ""]
        for row in result["common_confusions"]:
            lines.append(
                f"- `{row['actual']}` predicted as `{row['predicted']}`: {row['count']}"
            )

    lines += [
        "",
        "## Data caveat",
        "",
        result["data_note"],
        "",
        f"Confusion matrix: `{result['confusion_matrix_png']}`.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    result = evaluate(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "evaluation.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report = render_report(result)
    (args.output_dir / "report.md").write_text(report, encoding="utf-8")

    print(
        f"macro-F1={result['intent']['macro_f1']:.4f}  "
        f"accuracy={result['intent']['accuracy']:.4f}  "
        f"entity-F1={result['entities']['f1']:.4f}  "
        f"ECE={result['calibration']['ece_calibrated']:.4f}"
    )
    print(f"Wrote report and metrics to {args.output_dir}")

    if args.fail_under and result["intent"]["macro_f1"] < args.fail_under:
        raise SystemExit(
            f"Macro-F1 {result['intent']['macro_f1']:.4f} is below "
            f"--fail-under {args.fail_under:.4f}"
        )


if __name__ == "__main__":
    main()
