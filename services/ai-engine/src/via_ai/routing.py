"""Model selection and AI configuration (from environment variables).

    VIA_AI_PROVIDER        none (default) | groq | anthropic
    VIA_AI_MODEL           default model id (default depends on the provider:
                           groq -> openai/gpt-oss-120b, anthropic -> claude-opus-5-5)
    VIA_AI_MODEL_<TASK>    per-task override, e.g. VIA_AI_MODEL_DESIGN_REVIEW
    VIA_AI_EFFORT          default effort: low | medium | high | xhigh | max (default: high)

API keys are not part of this config: each provider reads its own from the
environment (Groq: GROQ_API_KEY; Anthropic: ANTHROPIC_API_KEY or an `ant auth` profile).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

DEFAULT_MODEL = "claude-opus-5-5"
PROVIDERS = ("none", "groq", "anthropic")
#: The model used when VIA_AI_MODEL is unset, per provider.
DEFAULT_MODELS = {"groq": "openai/gpt-oss-120b", "anthropic": "claude-opus-5-5"}


def default_model_for(provider: str) -> str:
    return DEFAULT_MODELS.get(provider, DEFAULT_MODEL)


EFFORTS = ("low", "medium", "high", "xhigh", "max")


class Task(StrEnum):
    """What a model call is for. New features add a task; routing picks the model."""

    DESIGN_REVIEW = "design_review"
    EXPLAIN = "explain"
    SUMMARIZE = "summarize"
    EXTRACT = "extract"


@dataclass(frozen=True)
class ModelRouting:
    default_model: str = DEFAULT_MODEL
    by_task: Mapping[Task, str] = field(default_factory=dict)

    def model_for(self, task: Task | None) -> str:
        if task is not None and task in self.by_task:
            return self.by_task[task]
        return self.default_model


@dataclass(frozen=True)
class AIConfig:
    provider: str = "none"
    routing: ModelRouting = field(default_factory=ModelRouting)
    effort: str = "high"
    #: Per-request token budgets. Groq counts prompt + reserved answer against the plan's tokens-per-minute
    #: limit, so the defaults suit its free tier; raise them on a paid plan.
    max_input_tokens: int = 4500
    max_output_tokens: int = 4000

    @property
    def enabled(self) -> bool:
        return self.provider != "none"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AIConfig:
        env = os.environ if env is None else env
        provider = (env.get("VIA_AI_PROVIDER") or "none").strip().lower()
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown VIA_AI_PROVIDER {provider!r}; expected one of {', '.join(PROVIDERS)}")
        effort = (env.get("VIA_AI_EFFORT") or "high").strip().lower()
        if effort not in EFFORTS:
            raise ValueError(f"Unknown VIA_AI_EFFORT {effort!r}; expected one of {', '.join(EFFORTS)}")
        by_task = {
            task: env[f"VIA_AI_MODEL_{task.value.upper()}"].strip()
            for task in Task
            if env.get(f"VIA_AI_MODEL_{task.value.upper()}", "").strip()
        }
        model = (env.get("VIA_AI_MODEL") or "").strip() or default_model_for(provider)
        routing = ModelRouting(default_model=model, by_task=by_task)
        budgets = {}
        for key, name in (
            ("max_input_tokens", "VIA_AI_MAX_INPUT_TOKENS"),
            ("max_output_tokens", "VIA_AI_MAX_OUTPUT_TOKENS"),
        ):
            raw = (env.get(name) or "").strip()
            if raw:
                if not raw.isdigit() or int(raw) < 500:
                    raise ValueError(f"{name} must be a whole number of at least 500")
                budgets[key] = int(raw)
        return cls(provider=provider, routing=routing, effort=effort, **budgets)
