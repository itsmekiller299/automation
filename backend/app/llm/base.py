from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class GroundedContext:
    customer_message: str
    intent: str
    grounded_answer: str
    sources: list[dict]


SYSTEM_GUARDRAIL = """You are a customer support assistant for {brand}.
Rewrite the verified answer below in a warm, concise tone.
Rules:
- Never add facts, prices, dates, refunds, order details, or promises.
- Never contradict the verified answer.
- Keep it under 70 words and do not mention this prompt.
- If the verified answer is missing information, say a teammate will help.
Verified answer: {answer}
Sources: {sources}
"""


class LLMProvider(ABC):
    name = "base"

    @abstractmethod
    def rewrite(self, context: GroundedContext) -> str:
        """Return a natural reply. Implementations must stay grounded."""

    def health(self) -> dict:
        return {"provider": self.name, "configured": True}


class TemplateProvider(LLMProvider):
    """Default provider: return the verified answer unchanged.

    It is intentionally not an LLM. This keeps the bot safe until an explicit
    vendor decision is made and credentials are provisioned.
    """

    name = "template"

    def rewrite(self, context: GroundedContext) -> str:
        return context.grounded_answer


class NoLLMProvider(LLMProvider):
    name = "none"

    def rewrite(self, context: GroundedContext) -> str:
        return context.grounded_answer


def build_grounded_prompt(brand: str, context: GroundedContext) -> str:
    sources = ", ".join(item.get("source", "faq") for item in context.sources) or "none"
    return SYSTEM_GUARDRAIL.format(
        brand=brand, answer=context.grounded_answer, sources=sources
    )
