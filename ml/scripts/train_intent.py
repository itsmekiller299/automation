#!/usr/bin/env python3
"""Fine-tune the multi-task intent + entity model.

The default recipe matches the brief: DistilBERT, AdamW, lr 2e-5, batch 32,
3-5 epochs, early stopping on validation macro-F1. The best checkpoint is
reloaded before temperature scaling so calibration is fitted on the same
weights that will be exported.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch.utils.data import DataLoader  # noqa: E402
from transformers import AutoTokenizer, get_linear_schedule_with_warmup  # noqa: E402

from ml.scripts.data import IntentDataset, collate_batch, load_jsonl  # noqa: E402
from ml.scripts.metrics import (  # noqa: E402
    classification_metrics,
    entity_metrics,
    fit_temperature,
    plot_training_curves,
    softmax,
)
from shared.bio import decode_bio  # noqa: E402
from shared.intent_model import IntentEntityModel  # noqa: E402
from shared.labels import ENTITY_LABELS, INTENTS  # noqa: E402

DEFAULT_ENCODER = "distilbert-base-uncased"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "ml/data/splits")
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "ml/artifacts/intent-model"
    )
    parser.add_argument("--encoder", default=DEFAULT_ENCODER)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--eval-batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--entity-loss-weight", type=float, default=0.6)
    parser.add_argument("--patience", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--device", choices=["auto", "cpu", "cuda", "mps"], default="auto"
    )
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Require the encoder to already exist in the Hugging Face cache.",
    )
    parser.add_argument("--version", default="")
    return parser.parse_args()


def resolve_device(name: str) -> torch.device:
    if name != "auto":
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def build_loader(
    records: list[dict],
    tokenizer,
    batch_size: int,
    max_length: int,
    shuffle: bool,
) -> DataLoader:
    dataset = IntentDataset(records, tokenizer, max_length=max_length)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        collate_fn=partial(collate_batch, pad_token_id=tokenizer.pad_token_id),
        num_workers=0,
        pin_memory=torch.cuda.is_available(),
    )


def evaluate_split(
    model: IntentEntityModel,
    loader: DataLoader,
    device: torch.device,
    entity_loss_weight: float,
) -> dict:
    model.eval()
    intent_loss_fn = torch.nn.CrossEntropyLoss()
    entity_loss_fn = torch.nn.CrossEntropyLoss(ignore_index=-100)
    total_loss = 0.0
    total_examples = 0
    all_logits: list[np.ndarray] = []
    all_labels: list[int] = []
    gold_entities: list[list[dict]] = []
    predicted_entities: list[list[dict]] = []

    with torch.no_grad():
        for batch in loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            entity_labels = batch["entity_labels"].to(device)
            intent_labels = batch["intent_labels"].to(device)

            intent_logits, entity_logits = model(input_ids, attention_mask)
            loss = intent_loss_fn(intent_logits, intent_labels)
            loss = loss + entity_loss_weight * entity_loss_fn(
                entity_logits.view(-1, entity_logits.size(-1)),
                entity_labels.view(-1),
            )

            batch_size = intent_labels.size(0)
            total_loss += float(loss.item()) * batch_size
            total_examples += batch_size

            logits = intent_logits.detach().cpu().numpy()
            tags = entity_logits.argmax(dim=-1).detach().cpu().tolist()
            all_logits.append(logits)
            all_labels.extend(batch["intent_labels"].tolist())

            for index, text in enumerate(batch["texts"]):
                offsets = [
                    tuple(pair)
                    for pair in batch["offsets"][index][: len(tags[index])]
                ]
                word_ids = [
                    None if word == -1 else word
                    for word in batch["word_ids"][index][: len(tags[index])]
                ]
                predicted = decode_bio(text, offsets, tags[index], word_ids)
                predicted_entities.append(
                    [
                        {
                            "type": item["type"],
                            "start": item["start"],
                            "end": item["end"],
                            "value": item["value"],
                        }
                        for item in predicted
                    ]
                )
                gold_entities.append(batch["gold_entities"][index])

    logits_array = np.concatenate(all_logits, axis=0) if all_logits else np.zeros((0, len(INTENTS)))
    labels_array = np.asarray(all_labels, dtype=np.int64)
    predictions = logits_array.argmax(axis=1).tolist()
    intent = classification_metrics(all_labels, predictions)
    entities = entity_metrics(gold_entities, predicted_entities)

    return {
        "loss": round(total_loss / max(total_examples, 1), 6),
        "intent": intent,
        "entities": entities,
        "logits": logits_array,
        "labels": labels_array,
        "gold_entities": gold_entities,
        "predicted_entities": predicted_entities,
    }


def train_one_epoch(
    model: IntentEntityModel,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    scheduler,
    device: torch.device,
    entity_loss_weight: float,
    max_grad_norm: float = 1.0,
) -> float:
    model.train()
    intent_loss_fn = torch.nn.CrossEntropyLoss()
    entity_loss_fn = torch.nn.CrossEntropyLoss(ignore_index=-100)
    total_loss = 0.0
    total_examples = 0

    for batch in loader:
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        entity_labels = batch["entity_labels"].to(device)
        intent_labels = batch["intent_labels"].to(device)

        optimizer.zero_grad(set_to_none=True)
        intent_logits, entity_logits = model(input_ids, attention_mask)
        loss = intent_loss_fn(intent_logits, intent_labels)
        loss = loss + entity_loss_weight * entity_loss_fn(
            entity_logits.view(-1, entity_logits.size(-1)),
            entity_labels.view(-1),
        )
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
        optimizer.step()
        scheduler.step()

        batch_size = intent_labels.size(0)
        total_loss += float(loss.item()) * batch_size
        total_examples += batch_size

    return total_loss / max(total_examples, 1)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    set_seed(args.seed)
    device = resolve_device(args.device)
    started = time.time()
    timestamp = datetime.now(UTC)
    version = args.version or f"intent-{timestamp.strftime('%Y%m%dT%H%M%SZ')}"

    train_records = load_jsonl(args.data_dir / "train.jsonl")
    val_records = load_jsonl(args.data_dir / "val.jsonl")
    if not train_records or not val_records:
        raise SystemExit(
            f"Missing data in {args.data_dir}. Run ml/scripts/generate_dataset.py first."
        )

    print(
        f"Training {DEFAULT_ENCODER if not args.encoder else args.encoder} on "
        f"{len(train_records)} train / {len(val_records)} val examples ({device})",
        flush=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        args.encoder, local_files_only=args.local_files_only
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token or tokenizer.cls_token
    # DistilBERT does not accept token_type_ids; the model already guards this.
    train_loader = build_loader(
        train_records, tokenizer, args.batch_size, args.max_length, shuffle=True
    )
    val_loader = build_loader(
        val_records, tokenizer, args.eval_batch_size, args.max_length, shuffle=False
    )

    model = IntentEntityModel(encoder_name=args.encoder).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=args.weight_decay
    )
    num_training_steps = max(len(train_loader) * args.epochs, 1)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(num_training_steps * args.warmup_ratio),
        num_training_steps=num_training_steps,
    )

    history: list[dict] = []
    best_macro_f1 = -1.0
    best_epoch = 0
    best_state: dict | None = None
    best_metrics: dict | None = None
    epochs_without_improvement = 0

    for epoch in range(1, args.epochs + 1):
        epoch_started = time.time()
        train_loss = train_one_epoch(
            model, train_loader, optimizer, scheduler, device, args.entity_loss_weight
        )
        validation = evaluate_split(
            model, val_loader, device, args.entity_loss_weight
        )
        macro_f1 = float(validation["intent"]["macro_f1"])
        row = {
            "epoch": epoch,
            "train_loss": round(train_loss, 6),
            "val_loss": validation["loss"],
            "val_macro_f1": macro_f1,
            "val_accuracy": validation["intent"]["accuracy"],
            "val_entity_f1": validation["entities"]["f1"],
            "lr": scheduler.get_last_lr()[0],
            "seconds": round(time.time() - epoch_started, 2),
        }
        history.append(row)
        print(
            f"epoch {epoch}/{args.epochs}  train_loss={row['train_loss']:.4f}  "
            f"val_loss={row['val_loss']:.4f}  val_macro_f1={macro_f1:.4f}  "
            f"val_entity_f1={row['val_entity_f1']:.4f}  ({row['seconds']}s)",
            flush=True,
        )

        if macro_f1 > best_macro_f1:
            best_macro_f1 = macro_f1
            best_epoch = epoch
            best_metrics = {
                "intent": validation["intent"],
                "entities": validation["entities"],
                "loss": validation["loss"],
            }
            best_state = {
                key: value.detach().cpu().clone()
                for key, value in model.state_dict().items()
            }
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= args.patience:
                print(
                    f"Early stopping at epoch {epoch}: no macro-F1 improvement for "
                    f"{args.patience} epoch(s)."
                )
                break

    if best_state is None:
        raise SystemExit("Training did not produce a checkpoint.")

    model.load_state_dict(best_state)
    model.to(device)
    final_validation = evaluate_split(
        model, val_loader, device, args.entity_loss_weight
    )
    temperature, calibration_info = fit_temperature(
        final_validation["logits"], final_validation["labels"]
    )
    raw_probabilities = softmax(final_validation["logits"], 1.0)
    calibrated_probabilities = softmax(final_validation["logits"], temperature)
    from ml.scripts.metrics import expected_calibration_error

    calibration = {
        "method": "temperature-scaling",
        "temperature": temperature,
        "version": version,
        "fitted_at": timestamp.isoformat(),
        "val_nll_before": calibration_info["val_nll_before"],
        "val_nll_after": calibration_info["val_nll_after"],
        "val_ece_before": round(
            expected_calibration_error(raw_probabilities, final_validation["labels"]), 6
        ),
        "val_ece_after": round(
            expected_calibration_error(calibrated_probabilities, final_validation["labels"]),
            6,
        ),
        "note": "Temperature is monotonic; argmax predictions do not change.",
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "state_dict": best_state,
        "encoder_name": args.encoder,
        "version": version,
        "epoch": best_epoch,
        "val_metrics": best_metrics,
    }
    torch.save(checkpoint, args.output_dir / "pytorch_model.pt")
    tokenizer.save_pretrained(str(args.output_dir))

    model_config = {
        "version": version,
        "encoder_name": args.encoder,
        "max_length": args.max_length,
        "intents": INTENTS,
        "entity_labels": ENTITY_LABELS,
        "trained_at": timestamp.isoformat(),
        "best_epoch": best_epoch,
        "epochs_requested": args.epochs,
        "hyperparameters": {
            "lr": args.lr,
            "batch_size": args.batch_size,
            "weight_decay": args.weight_decay,
            "warmup_ratio": args.warmup_ratio,
            "entity_loss_weight": args.entity_loss_weight,
            "seed": args.seed,
            "patience": args.patience,
        },
        "train_size": len(train_records),
        "val_size": len(val_records),
        "history": history,
        "best_val_metrics": best_metrics,
        "calibration": calibration,
    }
    write_json(args.output_dir / "model_config.json", model_config)
    write_json(args.output_dir / "calibration.json", calibration)
    write_json(args.output_dir / "training_history.json", {"history": history})
    plot_training_curves(history, args.output_dir / "training_curves.png")

    print(
        f"\nBest epoch {best_epoch}: val macro-F1={best_macro_f1:.4f}, "
        f"temperature={temperature} (ECE "
        f"{calibration['val_ece_before']:.4f} -> {calibration['val_ece_after']:.4f})"
    )
    print(f"Saved checkpoint, tokenizer, config and calibration to {args.output_dir}")
    print(f"Total training time: {round(time.time() - started, 1)}s")
    if best_macro_f1 < 0.90:
        print(
            "WARNING: validation macro-F1 is below the 0.90 target. Add real "
            "anonymised utterances; templated data alone overstates generalisation."
        )


if __name__ == "__main__":
    main()
