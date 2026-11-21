"""AI provider interface and implementations."""

from __future__ import annotations

from via_ai.providers.base import (
    AIError,
    AIProvider,
    AIRefusedError,
    AIUnavailableError,
    Capabilities,
    CapabilityNotSupportedError,
    ChatMessage,
    StructuredResult,
    TextRequest,
    TextResult,
)
from via_ai.providers.disabled import DisabledProvider
from via_ai.routing import AIConfig


def create_provider(config: AIConfig) -> AIProvider:
    """The provider for this configuration. Disabled unless explicitly configured."""
    if config.provider == "anthropic":
        from via_ai.providers.anthropic import AnthropicProvider

        return AnthropicProvider(config)
    return DisabledProvider()


__all__ = [
    "AIError",
    "AIProvider",
    "AIRefusedError",
    "AIUnavailableError",
    "Capabilities",
    "CapabilityNotSupportedError",
    "ChatMessage",
    "DisabledProvider",
    "StructuredResult",
    "TextRequest",
    "TextResult",
    "create_provider",
]
