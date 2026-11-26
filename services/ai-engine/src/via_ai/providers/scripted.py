"""A provider that returns pre-written outputs, for tests and the evaluation harness.

It never pretends to be a model in production: it's only constructed explicitly by tests and
evaluation code, and its ``name`` says what it is.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from via_ai.providers.base import (
    AIProvider,
    Capabilities,
    CapabilityNotSupportedError,
    StructuredResult,
    TextRequest,
    TextResult,
    Usage,
)

Output = BaseModel | dict[str, Any] | Callable[[TextRequest, type[BaseModel]], BaseModel] | Exception


class ScriptedProvider(AIProvider):
    name = "scripted"

    def __init__(self, outputs: list[Output], *, external: bool = False) -> None:
        self.outputs = list(outputs)
        self.requests: list[TextRequest] = []
        self.capabilities = Capabilities(text=False, structured_output=True, embeddings=False, external=external)

    def generate_text(self, request: TextRequest) -> TextResult:
        raise CapabilityNotSupportedError("The scripted provider only returns structured outputs.")

    def generate_structured[T: BaseModel](self, request: TextRequest, schema: type[T]) -> StructuredResult[T]:
        self.requests.append(request)
        if not self.outputs:
            raise AssertionError("ScriptedProvider ran out of outputs")
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        if callable(out) and not isinstance(out, BaseModel):
            out = out(request, schema)
        data = out.model_dump() if isinstance(out, BaseModel) else out
        return StructuredResult(value=schema.model_validate(data), model="scripted", usage=Usage(10, 20))

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise CapabilityNotSupportedError("The scripted provider has no embeddings.")
