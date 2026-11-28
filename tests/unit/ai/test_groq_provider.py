"""Groq provider: request shape, effort mapping, structured output, refusals and errors (fake transport)."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from via_ai import (
    AIConfig,
    AIError,
    AIRefusedError,
    AIUnavailableError,
    CapabilityNotSupportedError,
    ChatMessage,
    ModelRouting,
    Task,
    TextRequest,
    create_provider,
)
from via_ai.providers.groq import API_URL, GroqProvider
from via_ai.routing import default_model_for

REQUEST = TextRequest(messages=[ChatMessage(role="user", content="hi")], system="Be brief.")


class Review(BaseModel):
    verdict: str
    issues: list[str]


class FakeTransport:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[tuple[str, dict, dict]] = []

    def __call__(self, url: str, headers: dict, body: dict) -> dict:
        self.calls.append((url, headers, body))
        return self.response


def reply(content: str = "Hello", finish: str = "stop", **message) -> dict:
    return {
        "model": "openai/gpt-oss-120b",
        "choices": [
            {"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": content, **message}}
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
    }


def provider(
    response: dict, model: str = "openai/gpt-oss-120b", effort: str = "high"
) -> tuple[GroqProvider, FakeTransport]:
    transport = FakeTransport(response)
    config = AIConfig(
        provider="groq",
        routing=ModelRouting(default_model=model, by_task={Task.SUMMARIZE: "llama-3.3-70b-versatile"}),
        effort=effort,
    )
    return GroqProvider(config, api_key="gsk_test", transport=transport), transport


def test_text_request_shape_and_result():
    p, t = provider(reply("Hello"))
    result = p.generate_text(REQUEST)
    url, headers, body = t.calls[0]
    assert url == API_URL
    assert headers["Authorization"] == "Bearer gsk_test"
    assert headers["User-Agent"].startswith("via-ai-engine/")  # not the blocked Python-urllib default
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["messages"] == [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "hi"}]
    assert body["reasoning_effort"] == "high"
    assert result.text == "Hello" and result.stop_reason == "stop"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (12, 3)


@pytest.mark.parametrize(
    ("effort", "expected"), [("low", "low"), ("medium", "medium"), ("xhigh", "high"), ("max", "high")]
)
def test_effort_maps_to_reasoning_effort(effort, expected):
    p, t = provider(reply(), effort=effort)
    p.generate_text(REQUEST)
    assert t.calls[0][2]["reasoning_effort"] == expected


def test_non_reasoning_models_get_no_effort_and_task_routing_applies():
    p, t = provider(reply())
    p.generate_text(TextRequest(messages=REQUEST.messages, task=Task.SUMMARIZE))
    body = t.calls[0][2]
    assert body["model"] == "llama-3.3-70b-versatile"
    assert "reasoning_effort" not in body


def test_structured_output_is_validated_against_the_schema():
    p, t = provider(reply(json.dumps({"verdict": "ok", "issues": ["a"]})))
    result = p.generate_structured(REQUEST, Review)
    fmt = t.calls[0][2]["response_format"]
    assert (
        fmt["type"] == "json_schema" and fmt["json_schema"]["name"] == "Review" and fmt["json_schema"]["strict"] is True
    )
    assert fmt["json_schema"]["schema"]["properties"]["verdict"]["type"] == "string"
    assert result.value == Review(verdict="ok", issues=["a"])


def test_structured_output_that_does_not_validate_raises_instead_of_returning_partial_data():
    p, _ = provider(reply('{"verdict": "ok"}'))
    with pytest.raises(AIError, match="did not match"):
        p.generate_structured(REQUEST, Review)


@pytest.mark.parametrize("response", [reply("", refusal="I can't help with that."), reply("", finish="content_filter")])
def test_refusals_raise(response):
    p, _ = provider(response)
    with pytest.raises(AIRefusedError):
        p.generate_text(REQUEST)


def test_no_embeddings_and_key_never_in_repr():
    p, _ = provider(reply())
    with pytest.raises(CapabilityNotSupportedError):
        p.embed(["x"])
    assert "gsk_test" not in repr(p)


def test_missing_key_means_ai_is_unavailable(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(AIUnavailableError, match="GROQ_API_KEY"):
        create_provider(AIConfig(provider="groq"))


def test_config_from_env_uses_the_groq_default_model():
    config = AIConfig.from_env({"VIA_AI_PROVIDER": "groq"})
    assert config.provider == "groq"
    assert config.routing.default_model == default_model_for("groq") == "openai/gpt-oss-120b"
    assert (
        AIConfig.from_env({"VIA_AI_PROVIDER": "groq", "VIA_AI_MODEL": "llama-3.3-70b-versatile"}).routing.default_model
        == "llama-3.3-70b-versatile"
    )
    with pytest.raises(ValueError, match="groq"):
        AIConfig.from_env({"VIA_AI_PROVIDER": "openai"})


def test_strict_schema_inlines_refs_requires_every_property_and_drops_unsupported_keywords():
    from via_ai.providers.groq import strict_schema
    from via_ai.schemas import DesignReview

    out = strict_schema(DesignReview.model_json_schema())
    text = json.dumps(out)
    assert "$ref" not in text and "$defs" not in text
    for bad in ('"default"', '"maxItems"', '"title"'):
        assert bad not in text

    def check(node):
        if isinstance(node, dict):
            if "properties" in node:
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                check(v)
        elif isinstance(node, list):
            for v in node:
                check(v)

    check(out)


def test_models_without_strict_mode_use_json_mode_with_the_schema_in_the_prompt():
    p, t = provider(reply(json.dumps({"verdict": "ok", "issues": []})), model="llama-3.3-70b-versatile")
    p.generate_structured(REQUEST, Review)
    body = t.calls[0][2]
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system" and '"verdict"' in body["messages"][0]["content"]
    assert body["messages"][0]["content"].startswith("Be brief.")


def test_json_mode_retries_once_when_groq_rejects_the_json():
    calls = []

    def flaky(url, headers, body):
        calls.append(body)
        if len(calls) == 1:
            raise AIError("Groq couldn't process the request: Failed to validate JSON.")
        return reply(json.dumps({"verdict": "ok", "issues": []}))

    config = AIConfig(provider="groq", routing=ModelRouting(default_model="llama-3.3-70b-versatile"))
    result = GroqProvider(config, api_key="k", transport=flaky).generate_structured(REQUEST, Review)
    assert result.value.verdict == "ok" and len(calls) == 2


GOOD = json.dumps({"verdict": "ok", "issues": []})


def sequence(*responses):
    """A transport returning (or raising) each item in turn; records the bodies it saw."""
    bodies: list[dict] = []
    items = list(responses)

    def transport(url, headers, body):
        bodies.append(json.loads(json.dumps(body)))
        item = items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return GroqProvider(AIConfig(provider="groq"), api_key="k", transport=transport), bodies


def test_json_wrapped_in_a_code_fence_or_prose_is_still_read_and_validated():
    for text in (f"```json\n{GOOD}\n```", f"Here is the review:\n{GOOD}\nHope that helps."):
        p, _ = sequence(reply(text))
        assert p.generate_structured(REQUEST, Review).value.verdict == "ok"


def test_a_reply_cut_off_by_the_token_limit_is_retried_with_a_bigger_budget():
    p, bodies = sequence(reply('{"verdict": "ok", "issu', finish="length"), reply(GOOD))
    assert p.generate_structured(REQUEST, Review).value.verdict == "ok"
    assert bodies[1]["max_completion_tokens"] > bodies[0]["max_completion_tokens"]


def test_a_reply_that_is_always_cut_off_says_so_instead_of_a_generic_error():
    cut = reply('{"verdict": "ok", "issu', finish="length")
    p, _ = sequence(cut, cut)
    with pytest.raises(AIError, match="ran out of room"):
        p.generate_structured(REQUEST, Review)


def test_groqs_json_generation_failure_is_retried_once_in_strict_mode_too():
    p, bodies = sequence(
        AIError("Groq couldn't process the request: Failed to generate JSON. Please adjust your prompt."), reply(GOOD)
    )
    assert p.generate_structured(REQUEST, Review).value.verdict == "ok" and len(bodies) == 2


def test_a_reply_that_does_not_fit_the_schema_is_retried_once_then_names_the_field():
    bad = reply('{"verdict": "ok"}')
    p, bodies = sequence(bad, bad)
    with pytest.raises(AIError, match="issues"):
        p.generate_structured(REQUEST, Review)
    assert len(bodies) == 2
