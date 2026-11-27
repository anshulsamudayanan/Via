"""API-side AI integration: configuration, consent-gated project context."""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from via_ai import AIConfig, AIProvider, AIUnavailableError, DisabledProvider, ModelRouting, Task, create_provider
from via_ai.routing import default_model_for
from via_api.config import Settings, get_settings

logger = logging.getLogger(__name__)


def ai_config(settings: Settings) -> AIConfig:
    by_task = {
        task: os.environ[f"VIA_AI_MODEL_{task.value.upper()}"].strip()
        for task in Task
        if os.environ.get(f"VIA_AI_MODEL_{task.value.upper()}", "").strip()
    }
    return AIConfig(
        provider=settings.ai_provider,
        routing=ModelRouting(
            default_model=settings.ai_model.strip() or default_model_for(settings.ai_provider), by_task=by_task
        ),
        effort=settings.ai_effort,
    )


@lru_cache
def get_ai_provider() -> AIProvider:
    """The configured provider. A provider that can't start (e.g. Groq without GROQ_API_KEY) leaves AI
    off, with a warning in the log, instead of failing every request."""
    try:
        return create_provider(ai_config(get_settings()))
    except AIUnavailableError as exc:
        logger.warning("AI is off: %s", exc)
        return DisabledProvider()
