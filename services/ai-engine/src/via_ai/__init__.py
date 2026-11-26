"""VIA AI foundation.

Stage 2 (Milestone 4) adds the first features: grounded explanations and design reviews
(:mod:`via_ai.orchestration`) with versioned prompts, strict output schemas and a verification
step that rejects outputs citing anything not in the context.

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

from via_ai.context import ContextFinding, ContextFocus, ContextProvider, ContextPurpose, ProjectContext
from via_ai.orchestration import AIResult, explain, review
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
from via_ai.schemas import DesignReview, Explanation, Recommendation
from via_ai.verification import VerificationReport, verify

__all__ = [
    "AIConfig",
    "AIError",
    "AIProvider",
    "AIRefusedError",
    "AIResult",
    "AIUnavailableError",
    "Capabilities",
    "CapabilityNotSupportedError",
    "ChatMessage",
    "ContextFinding",
    "ContextFocus",
    "ContextProvider",
    "ContextPurpose",
    "DesignReview",
    "Explanation",
    "ModelRouting",
    "ProjectContext",
    "Recommendation",
    "StructuredResult",
    "Task",
    "TextRequest",
    "TextResult",
    "VerificationReport",
    "create_provider",
    "explain",
    "review",
    "verify",
]
