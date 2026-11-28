"""AI features: explanations and design reviews, from a ``ProjectContext`` to verified structured output."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from pydantic import BaseModel

from via_ai.context import ProjectContext
from via_ai.prompts import PROMPT_VERSION, explain_messages, review_messages
from via_ai.providers import AIProvider, ChatMessage, TextRequest
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


def _call[T: BaseModel](provider: AIProvider, system: str, user: str, task: Task, schema: type[T],
                        context: ProjectContext) -> AIResult[T]:  # fmt: skip
    result = provider.generate_structured(
        TextRequest(messages=[ChatMessage(role="user", content=user)], system=system, task=task, max_tokens=16000),
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
    system, user = explain_messages(context, question)
    return _call(provider, system, user, Task.EXPLAIN, Explanation, context)


def review(provider: AIProvider, context: ProjectContext) -> AIResult[DesignReview]:
    system, user = review_messages(context)
    return _call(provider, system, user, Task.DESIGN_REVIEW, DesignReview, context)
