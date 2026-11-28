"""Provider-neutral request/response types and the AIProvider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from via_ai.routing import Task


class AIError(RuntimeError):
    """Base class for AI failures. Messages are safe to show users."""


class AIUnavailableError(AIError):
    """AI is disabled or not configured. Callers must not substitute made-up output."""


class CapabilityNotSupportedError(AIError):
    """The configured provider can't do this (e.g. embeddings on a text-only provider)."""


class AIRefusedError(AIError):
    """The model declined the request. Never replaced by fabricated output."""

    def __init__(self, message: str, category: str | None = None) -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class Capabilities:
    text: bool
    structured_output: bool
    embeddings: bool
    #: True when calls leave VIA's infrastructure (requires consent for project data).
    external: bool


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class TextRequest:
    messages: list[ChatMessage]
    system: str | None = None
    task: Task | None = None
    #: Overrides the configured effort for this call.
    effort: str | None = None
    max_tokens: int = 16000


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class TextResult:
    text: str
    model: str
    stop_reason: str | None
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    value: T
    model: str
    usage: Usage = field(default_factory=Usage)


class AIProvider(ABC):
    name: str
    capabilities: Capabilities
    #: Largest prompt (estimated tokens) the provider accepts per request; None means no limit set.
    input_token_budget: int | None = None

    @abstractmethod
    def generate_text(self, request: TextRequest) -> TextResult:
        """Free-form text generation."""

    @abstractmethod
    def generate_structured[T: BaseModel](self, request: TextRequest, schema: type[T]) -> StructuredResult[T]:
        """Output validated against ``schema``; raises instead of returning partial data."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Vector embeddings, one per input text."""
