from __future__ import annotations

import json

import httpx
import pytest
from app.llm import factory
from app.llm.anthropic import AnthropicProvider, is_grounded_reply
from app.llm.base import GroundedContext, TemplateProvider

GROUNDED = "The Aria Lamp is priced at $89. The price shown on the Aria Lamp product page is always the current verified price."
CONTEXT = GroundedContext(
    customer_message="How much is the Aria Lamp?",
    intent="pricing",
    grounded_answer=GROUNDED,
    sources=[{"source": "catalog://aria-lamp/price"}],
)


def test_grounding_gate_accepts_known_numbers_and_urls() -> None:
    assert is_grounded_reply("The Aria Lamp is $89 — that is the current price.", GROUNDED)


def test_grounding_gate_rejects_invented_numbers() -> None:
    assert not is_grounded_reply("The Aria Lamp is $79 today only.", GROUNDED)


def test_grounding_gate_rejects_invented_links() -> None:
    assert not is_grounded_reply("Order it at https://evil.example/lamp", GROUNDED)


def test_grounding_gate_rejects_prompt_leakage() -> None:
    assert not is_grounded_reply("Verified answer: The Aria Lamp is $89.", GROUNDED)


def _provider(handler, **kwargs) -> AnthropicProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return AnthropicProvider("test-key", "claude-test", client=client, **kwargs)


def test_rewrite_sends_guardrail_and_returns_grounded_text() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["api_key"] = request.headers.get("x-api-key")
        seen["version"] = request.headers.get("anthropic-version")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": "The Aria Lamp is $89. That is the verified price.",
                    }
                ]
            },
        )

    provider = _provider(handler)
    assert provider.rewrite(CONTEXT) == "The Aria Lamp is $89. That is the verified price."
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["api_key"] == "test-key"
    assert seen["version"] == "2023-06-01"
    assert seen["body"]["model"] == "claude-test"
    assert "catalog://aria-lamp/price" in seen["body"]["system"]
    assert "untrusted data" in seen["body"]["system"]
    assert seen["body"]["temperature"] == 0.2


def test_rewrite_falls_back_when_model_invents_a_price() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "It is on sale for $79."}]},
        )

    assert _provider(handler).rewrite(CONTEXT) == GROUNDED


def test_rewrite_raises_on_vendor_error_so_manager_falls_back() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(529, json={"error": {"message": "overloaded"}})

    with pytest.raises(RuntimeError, match="529"):
        _provider(handler).rewrite(CONTEXT)


def test_provider_requires_credentials() -> None:
    with pytest.raises(ValueError):
        AnthropicProvider("", "claude-test")
    with pytest.raises(ValueError):
        AnthropicProvider("test-key", "")


def test_factory_fails_closed_without_credentials(monkeypatch) -> None:
    monkeypatch.setattr(factory.settings, "llm_provider", "anthropic")
    monkeypatch.setattr(factory.settings, "llm_api_key", "")
    factory.get_llm_provider.cache_clear()
    try:
        assert isinstance(factory.get_llm_provider(), TemplateProvider)
    finally:
        factory.get_llm_provider.cache_clear()


def test_factory_builds_anthropic_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(factory.settings, "llm_provider", "anthropic")
    monkeypatch.setattr(factory.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(factory.settings, "llm_model", "claude-test")
    factory.get_llm_provider.cache_clear()
    try:
        provider = factory.get_llm_provider()
        assert isinstance(provider, AnthropicProvider)
        assert provider.health()["model"] == "claude-test"
    finally:
        factory.get_llm_provider.cache_clear()
