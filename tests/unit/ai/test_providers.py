"""AI provider interface: disabled default, Anthropic adapter (fake client), routing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from via_ai import (
    AIConfig,
    AIRefusedError,
    AIUnavailableError,
    CapabilityNotSupportedError,
    ChatMessage,
    ModelRouting,
    Task,
    TextRequest,
    create_provider,
)
from via_ai.providers.anthropic import AnthropicProvider
from via_ai.providers.disabled import DisabledProvider

REQUEST = TextRequest(messages=[ChatMessage(role="user", content="hi")], system="Be brief.")


class Review(BaseModel):
    verdict: str
    issues: list[str]


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def fake_client(response):
    messages = FakeMessages(response)
    return SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages)), messages


def text_response(text="Hello", stop_reason="end_turn", **extra):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        model="claude-opus-5-5",
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=12, output_tokens=3),
        **extra,
    )


def test_ai_is_disabled_by_default():
    config = AIConfig.from_env({})
    assert (config.provider, config.enabled, config.routing.default_model, config.effort) == (
        "none",
        False,
        "claude-opus-5-5",
        "high",
    )
    provider = create_provider(config)
    assert isinstance(provider, DisabledProvider)
    for call in (
        lambda: provider.generate_text(REQUEST),
        lambda: provider.generate_structured(REQUEST, Review),
        lambda: provider.embed(["x"]),
    ):
        with pytest.raises(AIUnavailableError, match="not enabled"):
            call()


def test_config_from_env_validates_and_routes_tasks():
    config = AIConfig.from_env(
        {"VIA_AI_PROVIDER": "Anthropic", "VIA_AI_EFFORT": "medium", "VIA_AI_MODEL_SUMMARIZE": "claude-sonnet-5-5"}
    )
    assert config.provider == "anthropic" and config.effort == "medium"
    assert config.routing.model_for(Task.SUMMARIZE) == "claude-sonnet-5-5"
    assert config.routing.model_for(Task.DESIGN_REVIEW) == "claude-opus-5-5"
    assert config.routing.model_for(None) == "claude-opus-5-5"
    with pytest.raises(ValueError, match="VIA_AI_PROVIDER"):
        AIConfig.from_env({"VIA_AI_PROVIDER": "openai"})
    with pytest.raises(ValueError, match="VIA_AI_EFFORT"):
        AIConfig.from_env({"VIA_AI_EFFORT": "extreme"})


def anthropic_provider(response, **config):
    client, messages = fake_client(response)
    return AnthropicProvider(AIConfig(provider="anthropic", **config), client=client), messages


def test_anthropic_text_request_shape():
    provider, messages = anthropic_provider(text_response("Looks fine."))
    result = provider.generate_text(REQUEST)
    assert (result.text, result.model, result.usage.output_tokens) == ("Looks fine.", "claude-opus-5-5", 3)
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"] == {"effort": "high"}
    assert call["system"] == "Be brief."
    assert call["messages"] == [{"role": "user", "content": "hi"}]
    # Server-side refusal fallbacks opted in; thinking left at the model default (adaptive).
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in call


def test_anthropic_routes_by_task_and_effort_override():
    routing = ModelRouting(by_task={Task.SUMMARIZE: "claude-sonnet-5-5"})
    provider, messages = anthropic_provider(text_response(), routing=routing)
    provider.generate_text(TextRequest(messages=REQUEST.messages, task=Task.SUMMARIZE, effort="low"))
    assert (messages.calls[0]["model"], messages.calls[0]["output_config"]) == ("claude-sonnet-5-5", {"effort": "low"})


def test_anthropic_refusals_raise_instead_of_returning_output():
    refusal = text_response("", stop_reason="refusal", stop_details=SimpleNamespace(category="cyber"))
    provider, _ = anthropic_provider(refusal)
    with pytest.raises(AIRefusedError) as info:
        provider.generate_text(REQUEST)
    assert info.value.category == "cyber"


def test_anthropic_structured_output_is_validated():
    parsed = Review(verdict="ok", issues=[])
    provider, messages = anthropic_provider(SimpleNamespace(**vars(text_response()), parsed_output=parsed))
    result = provider.generate_structured(REQUEST, Review)
    assert result.value == parsed
    assert messages.calls[0]["output_format"] is Review
    assert "fallbacks" not in messages.calls[0]  # messages.parse has no fallback support


def test_anthropic_structured_output_mismatch_is_an_error():
    from via_ai import AIError

    provider, _ = anthropic_provider(SimpleNamespace(**vars(text_response()), parsed_output=None))
    with pytest.raises(AIError, match="expected structure"):
        provider.generate_structured(REQUEST, Review)


def test_anthropic_has_no_embeddings():
    provider, _ = anthropic_provider(text_response())
    assert provider.capabilities.embeddings is False and provider.capabilities.external is True
    with pytest.raises(CapabilityNotSupportedError):
        provider.embed(["text"])


def test_real_sdk_client_is_constructed_without_network(monkeypatch):
    pytest.importorskip("anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")
    provider = AnthropicProvider(AIConfig(provider="anthropic"))
    assert hasattr(provider.client.beta.messages, "create") and hasattr(provider.client.messages, "parse")
