from __future__ import annotations

import logging
from functools import lru_cache

from app.config import settings
from app.llm.base import LLMProvider, NoLLMProvider, TemplateProvider

logger = logging.getLogger(__name__)


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Build the configured provider, failing closed when configuration is missing.

    Providers must implement LLMProvider and stay grounded; see
    `app.llm.anthropic.is_grounded_reply` for the output gate.
    """
    if settings.llm_provider == "none":
        return NoLLMProvider()
    if settings.llm_provider == "anthropic":
        if not settings.llm_api_key or not settings.llm_model:
            logger.warning(
                "LLM_PROVIDER=anthropic but LLM_API_KEY/LLM_MODEL is missing; using template"
            )
            return TemplateProvider()
        # Imported lazily so the default install never imports vendor code paths.
        from app.llm.anthropic import AnthropicProvider

        return AnthropicProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url or "https://api.anthropic.com",
            version=settings.llm_anthropic_version,
            timeout=settings.llm_timeout_seconds,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )
    if settings.llm_provider == "template":
        return TemplateProvider()
    logger.warning("Unknown LLM_PROVIDER=%s; using template", settings.llm_provider)
    return TemplateProvider()
