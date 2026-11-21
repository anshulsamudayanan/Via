"""Project context: the only shape in which project data may reach a model.

A ``ProjectContext`` is a deliberately small, structured summary of a parsed
design (counts, layers, net names, component list). It never contains source
files, the full normalized geometry, user emails or other projects' data.

The API implements :class:`ContextProvider` (``via_api.ai.context``): it checks
the caller's project access and, for external providers, an active
``external_ai_processing`` consent for that project before building one.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

#: Caps keep context small and bounded; truncation is always reported.
MAX_COMPONENTS = 500
MAX_NETS = 1000


class ContextPurpose(StrEnum):
    DESIGN_REVIEW = "design_review"


class ContextComponent(BaseModel):
    model_config = ConfigDict(frozen=True)

    reference: str
    value: str | None
    footprint: str
    side: str


class ContextLayer(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    kind: str
    side: str


class ProjectContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    purpose: ContextPurpose
    project_id: uuid.UUID
    design_id: uuid.UUID
    revision_id: uuid.UUID
    revision_number: int
    design_name: str
    source_format: str
    stats: dict[str, float | int | None]
    layers: list[ContextLayer]
    net_names: list[str]
    components: list[ContextComponent]
    warnings: list[str]
    truncated: dict[str, int] = Field(default_factory=dict, description="Items left out because of size caps, by field")


class ContextProvider(Protocol):
    def build(
        self, *, user_id: uuid.UUID, design_id: uuid.UUID, purpose: ContextPurpose, external: bool
    ) -> ProjectContext:
        """Build context for a model call, enforcing access and consent. Raises on denial."""
        ...
