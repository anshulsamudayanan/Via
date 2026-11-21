"""The default provider: AI is off, and every call says so."""

from __future__ import annotations

from pydantic import BaseModel

from via_ai.providers.base import (
    AIProvider,
    AIUnavailableError,
    Capabilities,
    StructuredResult,
    TextRequest,
    TextResult,
)

MESSAGE = "AI features are not enabled on this VIA installation."


class DisabledProvider(AIProvider):
    name = "none"
    capabilities = Capabilities(text=False, structured_output=False, embeddings=False, external=False)

    def generate_text(self, request: TextRequest) -> TextResult:
        raise AIUnavailableError(MESSAGE)

    def generate_structured[T: BaseModel](self, request: TextRequest, schema: type[T]) -> StructuredResult[T]:
        raise AIUnavailableError(MESSAGE)

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise AIUnavailableError(MESSAGE)
