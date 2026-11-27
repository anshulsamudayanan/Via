"""Groq provider, using Groq's OpenAI-compatible Chat Completions API over HTTPS.

Set ``VIA_AI_PROVIDER=groq`` and put the key in ``GROQ_API_KEY``. VIA never stores
or logs the key; it is read from the environment when the provider is created and
sent only in the ``Authorization`` header to ``api.groq.com``.

No SDK or extra dependency: requests go through the standard library
(``urllib.request``), which honours ``HTTPS_PROXY`` like every other client here.

Behaviour:

* Model from :class:`~via_ai.routing.ModelRouting` (default ``openai/gpt-oss-120b``).
* Effort maps to Groq's ``reasoning_effort`` for the reasoning models that accept
  it (the ``openai/gpt-oss-*`` family): low -> low, medium -> medium, and
  high / xhigh / max -> high. Other models get no effort parameter.
* Structured output asks for ``response_format: json_schema`` built from the
  Pydantic schema, then validates the reply with that schema. Anything that does
  not validate raises :class:`AIError`; partial or repaired output is never returned.
* A model refusal (``message.refusal`` set, or ``finish_reason == "content_filter"``)
  raises :class:`AIRefusedError`; output is never invented.
* Embeddings: Groq has no embeddings endpoint, so ``embed`` raises
  :class:`CapabilityNotSupportedError`.
* Errors carry user-safe messages: a rejected key, rate limiting, an unavailable
  model and network failures are each reported plainly, without echoing the key.
"""

from __future__ import annotations

import contextlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from via_ai.providers.base import (
    AIError,
    AIProvider,
    AIRefusedError,
    AIUnavailableError,
    Capabilities,
    CapabilityNotSupportedError,
    StructuredResult,
    TextRequest,
    TextResult,
    Usage,
)
from via_ai.routing import AIConfig

API_URL = "https://api.groq.com/openai/v1/chat/completions"
USER_AGENT = "via-ai-engine/0.1 (+https://github.com/anshulsamudayanan/Via)"
TIMEOUT_SECONDS = 120
#: VIA effort -> Groq reasoning_effort (gpt-oss models accept low | medium | high).
REASONING_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}

#: (url, headers, body) -> parsed JSON response. Injectable for tests.
Transport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


def _http_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")  # noqa: S310 - fixed https URL
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:  # noqa: S310
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raw = ""
        with contextlib.suppress(OSError, UnicodeDecodeError):
            raw = exc.read().decode()
        detail = ""
        with contextlib.suppress(ValueError, AttributeError):
            detail = json.loads(raw).get("error", {}).get("message", "")
        if not detail and raw and not raw.lstrip().startswith("<"):
            # Plain-text replies from the edge, e.g. Cloudflare's "error code: 1010".
            detail = " ".join(raw.split())[:160]
        if exc.code == 401:
            raise AIError("Groq rejected the API key. Check GROQ_API_KEY.") from None
        if exc.code == 429:
            raise AIError("Groq's rate limit was reached. Try again in a minute.") from None
        if exc.code == 403:
            # Cloudflare in front of Groq answers 403 to blocked clients; Groq itself uses it for
            # keys or organisations without access to a model, or unsupported regions.
            reason = detail or "access denied"
            raise AIError(
                f"Groq refused the request (HTTP 403): {reason}. Check that the key's organisation can use the "
                "configured model and that Groq is available where this server runs."
            ) from None
        if exc.code == 404:
            raise AIError(f"Groq doesn't offer the configured model. {detail}".strip()) from None
        if exc.code == 400 and detail:
            raise AIError(f"Groq couldn't process the request: {detail}") from None
        raise AIError(f"Groq returned an error (HTTP {exc.code}). Try again later.") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AIError("Couldn't reach Groq. Check the server's internet connection.") from exc


def _usage(response: dict[str, Any]) -> Usage:
    usage = response.get("usage") or {}
    return Usage(
        input_tokens=int(usage.get("prompt_tokens") or 0), output_tokens=int(usage.get("completion_tokens") or 0)
    )


def _first_choice(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices:
        raise AIError("Groq returned no answer.")
    choice: dict[str, Any] = choices[0]
    message = choice.get("message") or {}
    if message.get("refusal") or choice.get("finish_reason") == "content_filter":
        raise AIRefusedError("The model declined this request.", "content_filter")
    return choice


def _schema_name(schema: type[BaseModel]) -> str:
    name = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in schema.__name__)
    return name[:64] or "result"


class GroqProvider(AIProvider):
    name = "groq"
    capabilities = Capabilities(text=True, structured_output=True, embeddings=False, external=True)

    def __init__(self, config: AIConfig, api_key: str | None = None, transport: Transport | None = None) -> None:
        self.config = config
        key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")
        if not key.strip():
            raise AIUnavailableError("VIA_AI_PROVIDER=groq needs a GROQ_API_KEY in the environment.")
        self._key = key.strip()
        self._post = transport or _http_post

    def __repr__(self) -> str:  # never show the key
        return f"GroqProvider(model={self.config.routing.default_model!r})"

    def _body(self, request: TextRequest) -> dict[str, Any]:
        model = self.config.routing.model_for(request.task)
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        body: dict[str, Any] = {"model": model, "messages": messages, "max_completion_tokens": request.max_tokens}
        if model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = REASONING_EFFORT.get(request.effort or self.config.effort, "medium")
        return body

    def _call(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # A real client name: Groq's edge rejects the default "Python-urllib" agent with 403.
            "User-Agent": USER_AGENT,
        }
        return self._post(API_URL, headers, body)

    def generate_text(self, request: TextRequest) -> TextResult:
        response = self._call(self._body(request))
        choice = _first_choice(response)
        text = (choice.get("message") or {}).get("content") or ""
        return TextResult(
            text=text,
            model=str(response.get("model", "")),
            stop_reason=choice.get("finish_reason"),
            usage=_usage(response),
        )

    def generate_structured[T: BaseModel](self, request: TextRequest, schema: type[T]) -> StructuredResult[T]:
        body = self._body(request)
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": _schema_name(schema), "schema": schema.model_json_schema()},
        }
        response = self._call(body)
        choice = _first_choice(response)
        content = (choice.get("message") or {}).get("content") or ""
        try:
            value = schema.model_validate_json(content)
        except ValidationError as exc:
            raise AIError("The model's response did not match the expected structure.") from exc
        return StructuredResult(value=value, model=str(response.get("model", "")), usage=_usage(response))

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise CapabilityNotSupportedError("The Groq provider does not offer embeddings.")
