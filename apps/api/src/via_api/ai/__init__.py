"""API-side AI integration: configuration, consent-gated project context."""

from __future__ import annotations

import os
from functools import lru_cache

from via_ai import AIConfig, AIProvider, ModelRouting, Task, create_provider
from via_api.config import Settings, get_settings


def ai_config(settings: Settings) -> AIConfig:
    by_task = {
        task: os.environ[f"VIA_AI_MODEL_{task.value.upper()}"].strip()
        for task in Task
        if os.environ.get(f"VIA_AI_MODEL_{task.value.upper()}", "").strip()
    }
    return AIConfig(
        provider=settings.ai_provider,
        routing=ModelRouting(default_model=settings.ai_model, by_task=by_task),
        effort=settings.ai_effort,
    )


@lru_cache
def get_ai_provider() -> AIProvider:
    return create_provider(ai_config(get_settings()))
