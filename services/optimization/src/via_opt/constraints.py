"""Constraints candidates must respect. They are never relaxed silently: a generator that can't meet
them doesn't propose the change, and validation re-checks every candidate and reports violations."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from via_pcb.analysis.checks.placement import CONNECTOR_REF, extent
from via_pcb.analysis.shapes import point_in_polygon
from via_pcb.models import BoundingBox, Component, PCBDesign


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


def violations(before: PCBDesign, after: PCBDesign, cons: Constraints) -> list[str]:
    out: list[str] = []
    old = {c.id: c for c in before.components if c.id}
    for c in after.components:
        o = old.get(c.id or "")
        moved = o is not None and (abs(o.position.x - c.position.x) > 1e-6 or abs(o.position.y - c.position.y) > 1e-6
                                   or abs(o.rotation - c.rotation) > 1e-6)  # fmt: skip
        if moved and o is not None and is_fixed(o, cons):
            out.append(f"{c.reference} is fixed but would move")
        if moved:
            e = extent(c)
            ob = after.outline.bbox
            if (
                e is not None
                and ob is not None
                and (e.min_x < ob.min_x or e.min_y < ob.min_y or e.max_x > ob.max_x or e.max_y > ob.max_y)
            ):
                out.append(f"{c.reference} would extend past the board outline")
            for poly in keepout_polygons(after):
                if e is not None and any(
                    point_in_polygon(p, poly)
                    for p in ((e.min_x, e.min_y), (e.max_x, e.max_y), (c.position.x, c.position.y))
                ):
                    out.append(f"{c.reference} would enter a keep-out zone")
    ob = after.outline.bbox
    if ob is not None:
        if cons.max_board_width_mm and ob.width > cons.max_board_width_mm + 1e-6:
            out.append(f"Board width {ob.width:.2f} mm exceeds the {cons.max_board_width_mm:g} mm limit")
        if cons.max_board_height_mm and ob.height > cons.max_board_height_mm + 1e-6:
            out.append(f"Board height {ob.height:.2f} mm exceeds the {cons.max_board_height_mm:g} mm limit")
    if cons.outline_fixed and before.outline.bbox != after.outline.bbox:
        out.append("The outline is fixed but would change")
    return out
