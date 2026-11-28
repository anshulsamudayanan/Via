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
* Structured output: on models with Groq's strict structured outputs (the
  ``openai/gpt-oss-*`` family) VIA sends ``json_schema`` with ``strict: true``, so
  decoding is constrained to the schema. Strict mode needs every property required,
  no ``$ref`` and no length/default keywords, so :func:`strict_schema` derives that
  shape from the Pydantic schema. Other models get JSON mode plus the schema in the
  system prompt, with one retry if Groq's own JSON check fails. Either way the
  reply is then validated by the full Pydantic schema; anything that does not
  validate raises :class:`AIError`, and partial or repaired output is never returned.
* A model refusal (``message.refusal`` set, or ``finish_reason == "content_filter"``)
  raises :class:`AIRefusedError`; output is never invented.
* Embeddings: Groq has no embeddings endpoint, so ``embed`` raises
  :class:`CapabilityNotSupportedError`.
* Errors carry user-safe messages: a rejected key, rate limiting, an unavailable
  model and network failures are each reported plainly, without echoing the key.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import re
import time
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

#: Longest rate-limit wait VIA sits through before retrying once; longer waits are reported to the user.
MAX_RATE_LIMIT_WAIT_SECONDS = 25.0


class AIRateLimitError(AIError):
    """Groq's rate limit; ``retry_after`` is how long Groq said to wait, when it said."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


_WAIT = re.compile(r"try again in (?:(\d+)m(?=\d))?(?:(\d+(?:\.\d+)?)(ms|s))?", re.IGNORECASE)


def _retry_after(message: str, header: str | None) -> float | None:
    """Seconds to wait, from Groq's ``Retry-After`` header or its "try again in 1m2.5s" text."""
    if header:
        with contextlib.suppress(ValueError):
            return float(header)
    m = _WAIT.search(message)
    if not m or not (m.group(1) or m.group(2)):
        return None
    seconds = float(int(m.group(1) or 0) * 60)
    if m.group(2):
        seconds += float(m.group(2)) / (1000 if m.group(3).lower() == "ms" else 1)
    return seconds


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
        if exc.code == 413:
            raise AIError(
                f"Groq says this request is too large for the account's limit ({detail or 'HTTP 413'}). "
                "Lower VIA_AI_MAX_INPUT_TOKENS / VIA_AI_MAX_OUTPUT_TOKENS or use a plan with a higher limit."
            ) from None
        if exc.code == 429:
            wait = _retry_after(detail, exc.headers.get("retry-after") if exc.headers else None)
            raise AIRateLimitError(
                f"Groq's rate limit was reached ({detail or 'HTTP 429'}). Try again in a minute.", wait
            ) from None
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
    except (urllib.error.URLError, TimeoutError, http.client.HTTPException, OSError) as exc:
        raise AIError("Couldn't reach Groq. Check the server's internet connection.") from exc
    except ValueError as exc:  # json.JSONDecodeError and bad UTF-8: a gateway page or a cut-off body
        raise AIError("Groq sent a reply VIA couldn't read. Try again.") from exc


def _json_text(content: str) -> str:
    """The JSON object in a reply that may be wrapped in a code fence or surrounded by prose.
    Nothing is repaired: the text between the first ``{`` and the last ``}`` still has to validate."""
    text = content.strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if 0 <= start < end else text


def _retryable(exc: AIError) -> bool:
    message = str(exc)
    return any(
        marker in message
        for marker in ("Failed to validate JSON", "Failed to generate JSON", "did not match", "ran out of room")
    )


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


#: JSON Schema keywords Groq's strict mode doesn't accept; Pydantic still enforces them afterwards.
_STRICT_DROP = {
    "default",
    "title",
    "maxItems",
    "minItems",
    "maxLength",
    "minLength",
    "pattern",
    "format",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "examples",
}


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """A strict-mode copy of a Pydantic JSON schema: ``$ref`` inlined, every object closed
    (``additionalProperties: false``) with all its properties required, unsupported keywords dropped."""
    defs: dict[str, Any] = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            target = defs[node["$ref"].rsplit("/", 1)[-1]]
            merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
            return walk(merged)
        out = {k: walk(v) for k, v in node.items() if k not in _STRICT_DROP and k != "$defs"}
        if out.get("type") == "object" or "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out.get("properties", {}).keys())
        return out

    return walk(schema)


def _supports_strict(model: str) -> bool:
    return model.startswith("openai/gpt-oss")


def _schema_name(schema: type[BaseModel]) -> str:
    name = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in schema.__name__)
    return name[:64] or "result"


class GroqProvider(AIProvider):
    name = "groq"
    capabilities = Capabilities(text=True, structured_output=True, embeddings=False, external=True)

    def __init__(
        self,
        config: AIConfig,
        api_key: str | None = None,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")
        if not key.strip():
            raise AIUnavailableError("VIA_AI_PROVIDER=groq needs a GROQ_API_KEY in the environment.")
        self._key = key.strip()
        self._post = transport or _http_post
        self._sleep = sleep
        self.input_token_budget = config.max_input_tokens

    def __repr__(self) -> str:  # never show the key
        return f"GroqProvider(model={self.config.routing.default_model!r})"

    def _body(self, request: TextRequest) -> dict[str, Any]:
        model = self.config.routing.model_for(request.task)
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": min(request.max_tokens, self.config.max_output_tokens),
        }
        if model.startswith("openai/gpt-oss"):
            effort = REASONING_EFFORT.get(request.effort or self.config.effort, "medium")
            if effort == "high" and self.config.max_output_tokens < 8000:
                effort = "medium"  # thinking shares the small answer budget; "high" would be cut off
            body["reasoning_effort"] = effort
        return body

    def _call(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # A real client name: Groq's edge rejects the default "Python-urllib" agent with 403.
            "User-Agent": USER_AGENT,
        }
        try:
            return self._post(API_URL, headers, body)
        except AIRateLimitError as exc:
            # Free-tier limits are per minute: a short wait usually clears it, so wait once and retry.
            if exc.retry_after is None or exc.retry_after > MAX_RATE_LIMIT_WAIT_SECONDS:
                raise
            self._sleep(exc.retry_after + 1.0)
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
        if _supports_strict(body["model"]):
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": _schema_name(schema),
                    "strict": True,
                    "schema": strict_schema(schema.model_json_schema()),
                },
            }
            attempts = 2
        else:
            # JSON mode: the schema goes in the system prompt; Groq checks the reply is JSON.
            spec = json.dumps(schema.model_json_schema())
            instruction = (
                f"Reply with a single JSON object that matches this JSON Schema exactly, and nothing else:\n{spec}"
            )
            messages = body["messages"]
            if messages and messages[0]["role"] == "system":
                messages[0] = {"role": "system", "content": f"{messages[0]['content']}\n\n{instruction}"}
            else:
                messages.insert(0, {"role": "system", "content": instruction})
            body["response_format"] = {"type": "json_object"}
            attempts = 2
        last: AIError | None = None
        for _ in range(attempts):
            try:
                response = self._call(body)
                choice = _first_choice(response)
                if choice.get("finish_reason") == "length":
                    # Reasoning models spend the same budget on thinking, so a long answer can be cut off.
                    # Think less on the retry instead of asking for more tokens (which counts against the limit).
                    if body.get("reasoning_effort") not in (None, "low"):
                        body["reasoning_effort"] = "low"
                    raise AIError("The model ran out of room before finishing its answer. Try again.")
                content = (choice.get("message") or {}).get("content") or ""
                value = schema.model_validate_json(_json_text(content))
                return StructuredResult(value=value, model=str(response.get("model", "")), usage=_usage(response))
            except ValidationError as exc:
                where = ", ".join(sorted({".".join(str(x) for x in e["loc"]) or "(root)" for e in exc.errors()}))
                last = AIError(
                    f"The model's response did not match the expected structure (problem with: {where[:200]})."
                )
            except AIError as exc:
                if isinstance(exc, AIRefusedError) or not _retryable(exc):
                    raise
                last = exc
        assert last is not None
        raise last

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise CapabilityNotSupportedError("The Groq provider does not offer embeddings.")
