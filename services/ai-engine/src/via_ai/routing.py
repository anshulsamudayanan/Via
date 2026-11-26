"""Model selection and AI configuration (from environment variables).

    VIA_AI_PROVIDER        none (default) | anthropic
    VIA_AI_MODEL           default model id (default: claude-opus-5-5)
    VIA_AI_MODEL_<TASK>    per-task override, e.g. VIA_AI_MODEL_DESIGN_REVIEW
    VIA_AI_EFFORT          default effort: low | medium | high | xhigh | max (default: high)

API keys are not part of this config: the provider SDK reads them from the
environment itself (for Anthropic: ANTHROPIC_API_KEY or an `ant auth` profile).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

DEFAULT_MODEL = "claude-opus-5-5"
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

    @property
    def enabled(self) -> bool:
        return self.provider != "none"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AIConfig:
        env = os.environ if env is None else env
        provider = (env.get("VIA_AI_PROVIDER") or "none").strip().lower()
        if provider not in {"none", "anthropic"}:
            raise ValueError(f"Unknown VIA_AI_PROVIDER {provider!r}; expected 'none' or 'anthropic'")
        effort = (env.get("VIA_AI_EFFORT") or "high").strip().lower()
        if effort not in EFFORTS:
            raise ValueError(f"Unknown VIA_AI_EFFORT {effort!r}; expected one of {', '.join(EFFORTS)}")
        by_task = {
            task: env[f"VIA_AI_MODEL_{task.value.upper()}"].strip()
            for task in Task
            if env.get(f"VIA_AI_MODEL_{task.value.upper()}", "").strip()
        }
        routing = ModelRouting(default_model=(env.get("VIA_AI_MODEL") or DEFAULT_MODEL).strip(), by_task=by_task)
        return cls(provider=provider, routing=routing, effort=effort)
