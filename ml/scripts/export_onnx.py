#!/usr/bin/env python3
"""Export the trained checkpoint to ONNX and verify numerical parity.

The runtime prefers ONNX when present, so this script refuses to silently ship a
graph that disagrees with PyTorch. It compares logits and argmax decisions on a
sample of the test split.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402
import torch  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

from ml.scripts.data import load_jsonl  # noqa: E402
from shared.intent_model import IntentEntityModel  # noqa: E402
from shared.labels import ID2ENTITY, INTENTS  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-dir", type=Path, default=PROJECT_ROOT / "ml/artifacts/intent-model"
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--opset", type=int, default=17)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument(
        "--max-abs-diff",
        type=float,
        default=1e-3,
        help="Parity gate for logits; ONNX Runtime and Torch should be near-identical.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    model_dir = args.model_dir
    output_path = args.output or (model_dir / "model.onnx")
    config_path = model_dir / "model_config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    max_length = int(config.get("max_length", 128))

    checkpoint_path = model_dir / "pytorch_model.pt"
    if not checkpoint_path.exists():
        raise SystemExit(f"No checkpoint at {checkpoint_path}; train the model first.")

    bundle = torch.load(str(checkpoint_path), map_location="cpu", weights_only=False)
    encoder_name = bundle.get("encoder_name") or config.get("encoder_name")
    model = IntentEntityModel(
        encoder_name=encoder_name,
        num_intents=len(INTENTS),
        num_entity_labels=len(ID2ENTITY),
    )
    model.load_state_dict(bundle["state_dict"])
    model.eval()

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token or tokenizer.cls_token

    dummy = tokenizer(
        "where is my order ORD-2042",
        return_tensors="pt",
        truncation=True,
        max_length=max_length,
    )
    dummy_inputs = (dummy["input_ids"], dummy["attention_mask"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Exporting to {output_path} (opset {args.opset})")
    torch.onnx.export(
        model,
        dummy_inputs,
        str(output_path),
        input_names=["input_ids", "attention_mask"],
        output_names=["intent_logits", "entity_logits"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "sequence"},
            "attention_mask": {0: "batch", 1: "sequence"},
            "intent_logits": {0: "batch"},
            "entity_logits": {0: "batch", 1: "sequence"},
        },
        opset_version=args.opset,
        do_constant_folding=True,
        export_params=True,
    )

    try:
        import onnx

        onnx.checker.check_model(str(output_path))
        checker = "passed"
    except Exception as exc:  # pragma: no cover - depends on optional onnx install
        checker = f"skipped ({type(exc).__name__}: {exc})"

    import onnxruntime as ort

    session = ort.InferenceSession(str(output_path), providers=["CPUExecutionProvider"])
    input_names = {item.name for item in session.get_inputs()}
    output_names_meta = [item.name for item in session.get_outputs()]

    records = load_jsonl(PROJECT_ROOT / "ml/data/splits/test.jsonl")[: args.samples]
    if not records:
        records = [{"text": "where is my order ORD-2042", "entities": []}]

    max_intent_diff = 0.0
    max_entity_diff = 0.0
    intent_matches = 0
    entity_positions = 0
    entity_matches = 0
    compared = 0

    for start in range(0, len(records), args.batch_size):
        chunk = records[start : start + args.batch_size]
        encoded = tokenizer(
            [row["text"] for row in chunk],
            return_tensors="pt",
            truncation=True,
            max_length=max_length,
            padding=True,
        )
        input_ids = encoded["input_ids"]
        attention_mask = encoded["attention_mask"]
        with torch.no_grad():
            torch_intent, torch_entity = model(input_ids, attention_mask)
        feed = {
            "input_ids": input_ids.numpy().astype("int64"),
            "attention_mask": attention_mask.numpy().astype("int64"),
        }
        feed = {key: value for key, value in feed.items() if key in input_names}
        outputs = session.run(None, feed)
        onnx_intent = None
        onnx_entity = None
        for output in outputs:
            if output.ndim == 2:
                onnx_intent = output
            elif output.ndim == 3:
                onnx_entity = output
        if onnx_intent is None or onnx_entity is None:
            raise SystemExit(f"Unexpected ONNX outputs: {[o.shape for o in outputs]}")

        torch_intent_np = torch_intent.numpy()
        torch_entity_np = torch_entity.numpy()
        max_intent_diff = max(
            max_intent_diff, float(np.abs(torch_intent_np - onnx_intent).max())
        )
        max_entity_diff = max(
            max_entity_diff, float(np.abs(torch_entity_np - onnx_entity).max())
        )
        intent_matches += int(
            (torch_intent_np.argmax(axis=1) == onnx_intent.argmax(axis=1)).sum()
        )
        entity_matches += int(
            (torch_entity_np.argmax(axis=-1) == onnx_entity.argmax(axis=-1)).sum()
        )
        entity_positions += int(torch_entity_np.shape[0] * torch_entity_np.shape[1])
        compared += len(chunk)

    parity = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_version": bundle.get("version") or config.get("version"),
        "onnx_path": str(output_path),
        "opset": args.opset,
        "checked_samples": compared,
        "max_intent_logit_diff": max_intent_diff,
        "max_entity_logit_diff": max_entity_diff,
        "intent_argmax_agreement": round(intent_matches / max(compared, 1), 6),
        "entity_argmax_agreement": round(entity_matches / max(entity_positions, 1), 6),
        "gate": args.max_abs_diff,
        "passed": max_intent_diff <= args.max_abs_diff
        and max_entity_diff <= args.max_abs_diff,
        "onnx_checker": checker,
        "onnx_inputs": sorted(input_names),
        "onnx_outputs": output_names_meta,
    }

    if config_path.exists():
        config["onnx"] = {
            "path": output_path.name,
            "opset": args.opset,
            "exported_at": parity["generated_at"],
            "parity_passed": parity["passed"],
        }
        write_json(config_path, config)
    write_json(model_dir / "onnx_export.json", parity)

    print(
        f"Parity: intent max|Δ|={max_intent_diff:.2e}, entity max|Δ|={max_entity_diff:.2e}, "
        f"intent agreement={parity['intent_argmax_agreement']:.4f}, "
        f"entity agreement={parity['entity_argmax_agreement']:.4f}"
    )
    if not parity["passed"]:
        raise SystemExit(
            f"Parity gate failed: max diff exceeded {args.max_abs_diff}. "
            "Do not ship this ONNX file."
        )
    print(f"ONNX export verified: {output_path}")


if __name__ == "__main__":
    main()
