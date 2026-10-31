from __future__ import annotations

import logging
import time
from functools import lru_cache

from app.config import settings
from app.nlu.rules import RuleBasedNLU
from app.nlu.types import NLUResult

logger = logging.getLogger(__name__)


class NLUService:
    """Selects the best available NLU backend with a safe rules fallback."""

    def __init__(self) -> None:
        self.fallback = RuleBasedNLU()
        self.backend = self._build_backend()

    def _build_backend(self):
        if settings.nlu_backend == "rules":
            logger.info("NLU backend: rules (configured)")
            return self.fallback

        try:
            from app.nlu.transformer import TransformerNLU

            backend = TransformerNLU(
                model_dir=settings.resolve_path(settings.nlu_model_dir),
                onnx_path=settings.resolve_path(settings.nlu_onnx_path),
            )
            logger.info("NLU backend: %s (%s)", backend.mode, backend.model_version)
            return backend
        except Exception as exc:
            if settings.nlu_backend == "transformer":
                logger.error("Transformer NLU unavailable, falling back to rules: %s", exc)
            else:
                logger.info("No transformer artifact loaded; using rules NLU: %s", exc)
            return self.fallback

    @property
    def version(self) -> str:
        return getattr(self.backend, "model_version", getattr(self.backend, "version", "rules-v1"))

    def predict(self, text: str) -> NLUResult:
        started = time.perf_counter()
        try:
            return self.backend.predict(text)
        except Exception:
            logger.exception("NLU inference failed; using rules fallback")
            result = self.fallback.predict(text)
            result.latency_ms = (time.perf_counter() - started) * 1000
            return result


@lru_cache
def get_nlu() -> NLUService:
    return NLUService()
