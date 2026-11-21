"""Anthropic (Claude) provider, using the official ``anthropic`` Python SDK.

Install with ``pip install 'via-ai-engine[anthropic]'`` and set
``VIA_AI_PROVIDER=anthropic``. Credentials are resolved by the SDK from the
environment (``ANTHROPIC_API_KEY``, ``ANTHROPIC_AUTH_TOKEN`` or an
``ant auth login`` profile); VIA never stores or logs them.

Behaviour:

* Model from :class:`~via_ai.routing.ModelRouting` (default ``claude-opus-5-5``),
  effort set explicitly on every call (``output_config.effort``); adaptive
  thinking is the model default, so ``thinking`` is not sent.
* Text calls opt into server-side refusal fallbacks (``fallbacks: "default"``,
  beta ``server-side-fallback-2026-07-01``): on a policy decline the API re-runs
  the request on a fallback model it chooses by refusal category.
* ``stop_reason == "refusal"`` (after fallbacks) raises :class:`AIRefusedError`;
  output is never invented.
* Structured output uses ``client.messages.parse(output_format=Schema)``, which
  validates the response against the Pydantic schema.
* Embeddings: the Claude API has no embeddings endpoint, so ``embed`` raises
  :class:`CapabilityNotSupportedError`. A dedicated embedding provider will be
  added when a feature needs vectors.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from via_ai.providers.base import (
    AIError,
    AIProvider,
    AIRefusedError,
    Capabilities,
    CapabilityNotSupportedError,
    StructuredResult,
    TextRequest,
    TextResult,
    Usage,
)
from via_ai.routing import AIConfig

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _usage(response: Any) -> Usage:
    usage = getattr(response, "usage", None)
    return Usage(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
    )


def _check_refusal(response: Any) -> None:
    if getattr(response, "stop_reason", None) == "refusal":
        details = getattr(response, "stop_details", None)
        raise AIRefusedError("The model declined this request.", getattr(details, "category", None))


class AnthropicProvider(AIProvider):
    name = "anthropic"
    capabilities = Capabilities(text=True, structured_output=True, embeddings=False, external=True)

    def __init__(self, config: AIConfig, client: Any | None = None) -> None:
        self.config = config
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # optional dependency
                raise AIError(
                    "VIA_AI_PROVIDER=anthropic requires the 'anthropic' package: pip install 'via-ai-engine[anthropic]'"
                ) from exc
            client = anthropic.Anthropic()
        self.client = client

    def _params(self, request: TextRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.config.routing.model_for(request.task),
            "max_tokens": request.max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "output_config": {"effort": request.effort or self.config.effort},
        }
        if request.system:
            params["system"] = request.system
        return params

    def generate_text(self, request: TextRequest) -> TextResult:
        response = self.client.beta.messages.create(
            **self._params(request),
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        _check_refusal(response)
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        return TextResult(text=text, model=response.model, stop_reason=response.stop_reason, usage=_usage(response))

    def generate_structured[T: BaseModel](self, request: TextRequest, schema: type[T]) -> StructuredResult[T]:
        response = self.client.messages.parse(**self._params(request), output_format=schema)
        _check_refusal(response)
        value = getattr(response, "parsed_output", None)
        if not isinstance(value, schema):
            raise AIError("The model's response did not match the expected structure.")
        return StructuredResult(value=value, model=response.model, usage=_usage(response))

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise CapabilityNotSupportedError("The Anthropic provider does not offer embeddings.")
