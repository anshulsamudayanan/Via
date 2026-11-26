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
MAX_FINDINGS = 200


class ContextPurpose(StrEnum):
    DESIGN_REVIEW = "design_review"
    EXPLAIN = "explain"


class ContextFinding(BaseModel):
    """A finding from an analysis run, as the model sees it (no internal ids beyond the finding id)."""

    model_config = ConfigDict(frozen=True)

    id: str
    check_id: str
    rule: str
    severity: str
    source: str
    verification: str
    title: str
    description: str
    components: list[str] = Field(default_factory=list)
    nets: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list, description="'label: value' lines, measured or quoted")


class ContextFocus(BaseModel):
    """The object a question is about: a finding, component, net or board region."""

    model_config = ConfigDict(frozen=True)

    kind: str = Field(description="finding | component | net | region")
    id: str
    details: dict[str, str | float | int | list[str] | None] = Field(default_factory=dict)


class ContextComponentRecord(BaseModel):
    """Component information stored for the project, with where it came from."""

    model_config = ConfigDict(frozen=True)

    references: list[str]
    manufacturer: str
    part_number: str
    description: str | None = None
    package: str | None = None
    specs: list[str] = Field(default_factory=list, description="'name: value unit (source, verified|unverified)'")
    verification: str = "unverified"


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
    #: Stage 2: analysis findings of the latest successful run (capped), the question's focus,
    #: rules from the project file and stored component records. All optional.
    analysis_run_id: uuid.UUID | None = None
    findings: list[ContextFinding] = Field(default_factory=list)
    focus: ContextFocus | None = None
    design_rules: dict[str, float | bool | str | None] = Field(default_factory=dict)
    component_records: list[ContextComponentRecord] = Field(default_factory=list)


class ContextProvider(Protocol):
    def build(
        self,
        *,
        user_id: uuid.UUID,
        design_id: uuid.UUID,
        purpose: ContextPurpose,
        external: bool,
        focus: tuple[str, str] | None = None,
        run_id: uuid.UUID | None = None,
    ) -> ProjectContext:
        """Build context for a model call, enforcing access and consent. Raises on denial."""
        ...
