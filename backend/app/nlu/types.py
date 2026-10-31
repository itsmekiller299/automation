from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class Entity:
    type: str
    value: str
    start: int
    end: int
    score: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class NLUResult:
    intent: str
    confidence: float
    entities: list[dict] = field(default_factory=list)
    top_intents: list[dict] = field(default_factory=list)
    model_version: str = "rules-v1"
    calibrated: bool = False
    source: str = "rules"
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "confidence": round(self.confidence, 4),
            "entities": self.entities,
            "top_intents": self.top_intents,
            "model_version": self.model_version,
            "calibrated": self.calibrated,
            "source": self.source,
            "latency_ms": round(self.latency_ms, 2),
        }

    def entity_values(self, entity_type: str) -> list[str]:
        return [e["value"] for e in self.entities if e.get("type") == entity_type]
