"""VIA AI foundation.

Stage 1 ships interfaces, not features: no part of VIA calls a model yet.

* :mod:`via_ai.providers`: the ``AIProvider`` interface (text generation,
  structured output, embeddings), a disabled default and an Anthropic adapter.
* :mod:`via_ai.routing`: model selection per task, configured from the environment.
* :mod:`via_ai.context`: the ``ProjectContext`` that future features will send to a
  model, and the ``ContextProvider`` protocol the API implements with
  authorization and consent checks.

Rules (docs/SECURITY.md): providers are disabled unless configured; API keys
come only from the environment; project data reaches an external model only
through an authorized, consented ``ContextProvider``; outputs are never
fabricated (a disabled or refusing provider raises instead of answering).
"""

from via_ai.context import ContextProvider, ContextPurpose, ProjectContext
from via_ai.providers import (
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
    create_provider,
)
from via_ai.routing import AIConfig, ModelRouting, Task

__all__ = [
    "AIConfig",
    "AIError",
    "AIProvider",
    "AIRefusedError",
    "AIUnavailableError",
    "Capabilities",
    "CapabilityNotSupportedError",
    "ChatMessage",
    "ContextProvider",
    "ContextPurpose",
    "ModelRouting",
    "ProjectContext",
    "StructuredResult",
    "Task",
    "TextRequest",
    "TextResult",
    "create_provider",
]
