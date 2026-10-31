from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.metrics import classification_report, confusion_matrix

from shared.labels import INTENTS

ENTITY_TYPES = ["ORDER_ID", "PRODUCT", "DATE"]


def classification_metrics(y_true: list[int], y_pred: list[int]) -> dict:
    labels = list(range(len(INTENTS)))
    report = classification_report(
        y_true,
        y_pred,
        labels=labels,
        target_names=INTENTS,
        output_dict=True,
        zero_division=0,
    )
    matrix = confusion_matrix(y_true, y_pred, labels=labels).tolist()
    per_intent = {
        intent: {
            "precision": round(float(report[intent]["precision"]), 4),
            "recall": round(float(report[intent]["recall"]), 4),
            "f1": round(float(report[intent]["f1-score"]), 4),
            "support": int(report[intent]["support"]),
        }
        for intent in INTENTS
    }
    return {
        "accuracy": round(float(report["accuracy"]), 4),
        "macro_f1": round(float(report["macro avg"]["f1-score"]), 4),
        "weighted_f1": round(float(report["weighted avg"]["f1-score"]), 4),
        "macro_precision": round(float(report["macro avg"]["precision"]), 4),
        "macro_recall": round(float(report["macro avg"]["recall"]), 4),
        "per_intent": per_intent,
        "confusion_matrix": matrix,
        "labels": INTENTS,
    }


def expected_calibration_error(
    probabilities: np.ndarray, labels: np.ndarray, bins: int = 10
) -> float:
    if len(probabilities) == 0:
        return 0.0
    confidences = probabilities.max(axis=1)
    predictions = probabilities.argmax(axis=1)
    correct = (predictions == labels).astype(float)
    ece = 0.0
    boundaries = np.linspace(0.0, 1.0, bins + 1)
    for lower, upper in zip(boundaries[:-1], boundaries[1:], strict=False):
        mask = (confidences > lower) & (confidences <= upper)
        if not mask.any():
            continue
        bin_accuracy = correct[mask].mean()
        bin_confidence = confidences[mask].mean()
        ece += (mask.sum() / len(confidences)) * abs(bin_accuracy - bin_confidence)
    return float(ece)


def negative_log_likelihood(probabilities: np.ndarray, labels: np.ndarray) -> float:
    if len(labels) == 0:
        return 0.0
    clipped = np.clip(probabilities, 1e-12, 1.0)
    return float(-np.log(clipped[np.arange(len(labels)), labels]).mean())


def softmax(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    scaled = logits / max(temperature, 1e-6)
    scaled = scaled - scaled.max(axis=1, keepdims=True)
    exp = np.exp(scaled)
    return exp / exp.sum(axis=1, keepdims=True)


def fit_temperature(logits: np.ndarray, labels: np.ndarray) -> tuple[float, dict]:
    """Grid-search temperature scaling by validation NLL.

    A single scalar keeps calibration monotonic and is cheap to audit. The grid
    is intentionally bounded; extreme temperatures usually signal a data issue.
    """
    best_temperature = 1.0
    best_nll = float("inf")
    for temperature in np.arange(0.5, 5.01, 0.05):
        nll = negative_log_likelihood(softmax(logits, float(temperature)), labels)
        if nll < best_nll:
            best_nll = nll
            best_temperature = float(temperature)
    before = negative_log_likelihood(softmax(logits, 1.0), labels)
    return round(best_temperature, 3), {
        "val_nll_before": round(before, 6),
        "val_nll_after": round(best_nll, 6),
    }


def entity_metrics(gold: list[list[dict]], predicted: list[list[dict]]) -> dict:
    """Exact-span micro precision/recall/F1, overall and per entity type."""
    counts = {entity_type: {"tp": 0, "fp": 0, "fn": 0} for entity_type in ENTITY_TYPES}
    for gold_entities, predicted_entities in zip(gold, predicted, strict=False):
        gold_spans = {
            (str(item.get("type")), int(item.get("start", 0)), int(item.get("end", 0)))
            for item in gold_entities
            if item.get("type") in ENTITY_TYPES
        }
        predicted_spans = {
            (str(item.get("type")), int(item.get("start", 0)), int(item.get("end", 0)))
            for item in predicted_entities
            if item.get("type") in ENTITY_TYPES
        }
        for span in predicted_spans:
            counts[span[0]]["tp" if span in gold_spans else "fp"] += 1
        for span in gold_spans - predicted_spans:
            counts[span[0]]["fn"] += 1

    def compute(tp: int, fp: int, fn: int) -> dict:
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": tp + fn,
        }

    per_type = {entity_type: compute(**counts[entity_type]) for entity_type in ENTITY_TYPES}
    total = {
        key: sum(counts[entity_type][key] for entity_type in ENTITY_TYPES)
        for key in ("tp", "fp", "fn")
    }
    overall = compute(**total)
    overall["per_type"] = per_type
    return overall


def save_confusion_matrix(matrix: list[list[int]], path: Path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns

        path.parent.mkdir(parents=True, exist_ok=True)
        plt.figure(figsize=(9, 7))
        sns.heatmap(
            matrix,
            annot=True,
            fmt="d",
            cmap="Greens",
            xticklabels=INTENTS,
            yticklabels=INTENTS,
            cbar=False,
        )
        plt.xlabel("Predicted")
        plt.ylabel("Actual")
        plt.xticks(rotation=40, ha="right")
        plt.yticks(rotation=0)
        plt.title("Intent confusion matrix")
        plt.tight_layout()
        plt.savefig(path, dpi=180)
        plt.close()
        return True
    except Exception:
        return False


def plot_training_curves(history: list[dict], path: Path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        epochs = [row["epoch"] for row in history]
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        axes[0].plot(epochs, [row["train_loss"] for row in history], marker="o", label="train")
        axes[0].plot(epochs, [row["val_loss"] for row in history], marker="o", label="val")
        axes[0].set_title("Loss")
        axes[0].set_xlabel("Epoch")
        axes[0].legend()
        axes[1].plot(epochs, [row["val_macro_f1"] for row in history], marker="o", color="#0f766e")
        axes[1].axhline(0.90, color="#b91c1c", linestyle="--", linewidth=1, label="target 0.90")
        axes[1].set_title("Validation macro-F1")
        axes[1].set_xlabel("Epoch")
        axes[1].set_ylim(0, 1.02)
        axes[1].legend()
        fig.tight_layout()
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=180)
        plt.close(fig)
        return True
    except Exception:
        return False
