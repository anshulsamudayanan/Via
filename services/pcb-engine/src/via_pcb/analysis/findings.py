"""The unified finding schema shared by every analysis source.

A finding states *what* was detected, *where* (objects, nets, components, board region),
*how we know* (source, evidence, confidence, verification) and *what to do about it*.
Persisted findings add identity, project/revision and review state in the API layer.

Rules for producers:
* Evidence is measured from the design or quoted from a rule; never invented.
* ``source`` is honest: a VIA heuristic is never reported as a KiCad DRC result, and an
  AI suggestion is never ``verified``.
* ``fingerprint`` identifies "the same issue" across revisions; it must not depend on
  values that change when the issue is fixed (e.g. a measured gap), only on what the
  issue is about (check, rule, objects).
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from via_pcb.models import BoundingBox, Point


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        """0 = most severe (for sorting)."""
        return list(Severity).index(self)


class Category(StrEnum):
    GEOMETRY = "geometry"
    BOARD_OUTLINE = "board_outline"
    DESIGN_RULES = "design_rules"
    CONNECTIVITY = "connectivity"
    ROUTING = "routing"
    PLACEMENT = "placement"
    MANUFACTURING = "manufacturing"
    THERMAL = "thermal"
    POWER = "power"
    SIGNAL_INTEGRITY = "signal_integrity"
    IMPORT = "import"


class Source(StrEnum):
    """Where a finding came from. Shown with every finding."""

    VIA_DETERMINISTIC = "via_deterministic"  # VIA's own algorithm on the parsed design
    KICAD_DRC = "kicad_drc"  # KiCad's design rule checker
    EXTERNAL_SIMULATION = "external_simulation"  # a simulator's result
    AI_SUGGESTION = "ai_suggestion"  # a language model; never verified by itself


class Verification(StrEnum):
    """How much the finding itself can be trusted, as produced (separate from user review)."""

    VERIFIED = "verified"  # exact computation on data the model represents exactly, or KiCad DRC
    HEURISTIC = "heuristic"  # deterministic but approximate or rule-of-thumb; needs engineering judgement
    UNVERIFIED = "unverified"  # e.g. AI suggestions: a hypothesis until checked


class ObjectKind(StrEnum):
    COMPONENT = "component"
    PAD = "pad"
    TRACK = "track"
    VIA = "via"
    ZONE = "zone"
    NET = "net"
    OUTLINE = "outline"
    LAYER = "layer"


class ObjectRef(_Model):
    kind: ObjectKind
    id: str = Field(description="The object's stable id in the design (net/layer: its name)")
    label: str | None = Field(default=None, description="Human-readable, e.g. 'R1 pad 2'")


class Region(_Model):
    """Where on the board, in board coordinates (mm)."""

    bbox: BoundingBox
    points: list[Point] = Field(default_factory=list, description="Exact markers, e.g. violation positions")
    layers: list[str] = Field(default_factory=list)


class Evidence(_Model):
    kind: str = Field(description="measurement | rule | source_data | tool_output | reference")
    label: str
    value: str = Field(description="As displayed, e.g. '0.12 mm' or 'open (2 chains)'")
    numeric_value: float | None = None
    unit: str | None = None
    expected: str | None = Field(default=None, description="The requirement it is compared with, if any")


class Finding(_Model):
    check_id: str
    rule: str = Field(description="Specific rule within the check, e.g. 'outline_open'")
    category: Category
    severity: Severity
    title: str
    description: str = Field(description="What was found, specific to this design")
    explanation: str = Field(description="Why it matters (engineering background)")
    objects: list[ObjectRef] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list, description="Reference designators involved")
    nets: list[str] = Field(default_factory=list)
    region: Region | None = None
    source: Source = Source.VIA_DETERMINISTIC
    verification: Verification = Verification.VERIFIED
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    suggested_resolution: str | None = None
    fingerprint: str = ""

    def with_fingerprint(self, *key: str) -> Finding:
        """Set ``fingerprint`` from check, rule and ``key`` (defaults to the sorted object ids)."""
        parts = key or tuple(sorted(f"{o.kind}:{o.id}" for o in self.objects))
        raw = "|".join((self.check_id, self.rule, *parts))
        self.fingerprint = hashlib.sha256(raw.encode()).hexdigest()[:32]
        return self


__all__ = [
    "Category",
    "Evidence",
    "Finding",
    "ObjectKind",
    "ObjectRef",
    "Region",
    "Severity",
    "Source",
    "Verification",
]
