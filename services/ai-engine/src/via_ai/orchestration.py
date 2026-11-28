"""AI features: explanations and design reviews, from a ``ProjectContext`` to verified structured output."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from via_ai.context import ProjectContext
from via_ai.prompts import PROMPT_VERSION, explain_messages, review_messages
from via_ai.providers import AIError, AIProvider, ChatMessage, TextRequest
from via_ai.providers.base import Usage
from via_ai.routing import Task
from via_ai.schemas import DesignReview, Explanation
from via_ai.verification import VerificationReport, context_json, verify


@dataclass(frozen=True)
class AIResult[T: BaseModel]:
    value: T
    report: VerificationReport
    model: str
    usage: Usage
    prompt_version: str
    context_sha256: str

    @property
    def accepted(self) -> bool:
        return self.report.ok


def _context_hash(context: ProjectContext) -> str:
    return hashlib.sha256(context_json(context).encode()).hexdigest()


def _schema_chars(schema: type[BaseModel]) -> int:
    """The response schema is sent with the prompt and counts against the provider's token limit."""
    return len(json.dumps(schema.model_json_schema()))


CHARS_PER_TOKEN = 3  # JSON tokenizes poorly; erring low only means trimming a little more


def fit_context(
    provider: AIProvider, context: ProjectContext, size_of: Callable[[ProjectContext], int]
) -> ProjectContext:
    """Trim the context until the prompt fits the provider's input budget. Lowest-priority data goes first
    (nets and components, then library knowledge, then the tail of the severity-ordered findings). What was
    left out is recorded in ``truncated`` so the model and the verifier work from exactly what it was shown."""
    budget = provider.input_token_budget
    if budget is None:
        return context
    # Trimmed in this order: board lists first, then knowledge (it only supplements), findings last.
    tiers = (("net_names", "components"), ("knowledge",), ("findings",))
    dropped = dict(context.truncated)
    current = context
    while size_of(current) // CHARS_PER_TOKEN > budget:
        tier = next((t for t in tiers if any(getattr(current, f) for f in t)), None)
        if tier is None:
            raise AIError("This design's context is too large for the configured AI input limit.")
        field = max(tier, key=lambda f: len(getattr(current, f)))
        items = getattr(current, field)
        keep = len(items) // 2
        dropped[field] = dropped.get(field, 0) + len(items) - keep
        current = current.model_copy(update={field: items[:keep], "truncated": dict(dropped)})
    return current


def _call[T: BaseModel](provider: AIProvider, system: str, user: str, task: Task, schema: type[T],
                        context: ProjectContext) -> AIResult[T]:  # fmt: skip
    result = provider.generate_structured(
        TextRequest(messages=[ChatMessage(role="user", content=user)], system=system, task=task, max_tokens=8000),
        schema,
    )
    return AIResult(
        value=result.value,
        report=verify(result.value, context),
        model=result.model,
        usage=result.usage,
        prompt_version=PROMPT_VERSION,
        context_sha256=_context_hash(context),
    )


def explain(provider: AIProvider, context: ProjectContext, question: str) -> AIResult[Explanation]:
    """Answer an engineering question about the design. Raises AIError subclasses on provider failure/refusal."""
    context = fit_context(
        provider, context, lambda c: sum(map(len, explain_messages(c, question))) + _schema_chars(Explanation)
    )
    system, user = explain_messages(context, question)
    return _call(provider, system, user, Task.EXPLAIN, Explanation, context)


def review(provider: AIProvider, context: ProjectContext) -> AIResult[DesignReview]:
    context = fit_context(provider, context, lambda c: sum(map(len, review_messages(c))) + _schema_chars(DesignReview))
    system, user = review_messages(context)
    return _call(provider, system, user, Task.DESIGN_REVIEW, DesignReview, context)
