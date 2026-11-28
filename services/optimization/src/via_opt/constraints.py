"""Constraints candidates must respect. They are never relaxed silently: a generator that can't meet
them doesn't propose the change, and validation re-checks every candidate and reports violations."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from via_pcb.analysis.checks.placement import CONNECTOR_REF
from via_pcb.models import BoundingBox, Component, PCBDesign


class Requirement(BaseModel):
    """An engineering requirement the engineer declares. VIA only evaluates kinds it has an evaluator for;
    every other kind is recorded as ``unverified`` and never treated as satisfied."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=64, description="e.g. 'impedance', 'length_matching', 'enclosure_fit'")
    description: str = Field(default="", max_length=300)
    hard: bool = Field(default=True, description="A hard requirement that can't be verified blocks validation")


class Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixed_components: list[str] = Field(default_factory=list, description="References that must not move")
    keep_locked_fixed: bool = Field(default=True, description="Components locked in KiCad don't move")
    keep_connectors_fixed: bool = Field(default=True, description="Connectors and mounting holes don't move")
    outline_fixed: bool = False
    edge_margin_mm: float = Field(default=1.0, ge=0, le=50, description="Kept between components and a new outline")
    component_gap_mm: float = Field(default=0.25, ge=0, le=20, description="Minimum gap between component extents")
    max_board_width_mm: float | None = Field(default=None, gt=0)
    max_board_height_mm: float | None = Field(default=None, gt=0)
    requirements: list[Requirement] = Field(default_factory=list, max_length=50)


_MOUNTING = re.compile(r"^(H|MH|MK|FID)\d", re.I)


def is_fixed(c: Component, cons: Constraints) -> bool:
    if c.reference in cons.fixed_components:
        return True
    if cons.keep_locked_fixed and c.locked:
        return True
    ref, fp = c.reference or "", c.footprint.lower()
    mechanical = bool(CONNECTOR_REF.match(ref) or _MOUNTING.match(ref)) or "connector" in fp or "mountinghole" in fp
    return cons.keep_connectors_fixed and mechanical


def overlaps(a: BoundingBox, b: BoundingBox, gap: float) -> bool:
    return not (
        a.max_x + gap <= b.min_x or b.max_x + gap <= a.min_x or a.max_y + gap <= b.min_y or b.max_y + gap <= a.min_y
    )


def keepout_polygons(design: PCBDesign) -> list[list[tuple[float, float]]]:
    """Keep-out zones that forbid footprints."""
    return [[(p.x, p.y) for p in z.outline] for z in design.zones
            if z.keepout and z.keepout_rules is not None and z.keepout_rules.footprints is False]  # fmt: skip
