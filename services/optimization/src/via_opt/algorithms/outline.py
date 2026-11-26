"""Area reduction: fit a rectangular outline to the content (routing untouched)."""

from __future__ import annotations

from via_opt.changes import Change, ChangeKind, Target
from via_opt.constraints import Constraints
from via_pcb.analysis.checks.placement import extent
from via_pcb.analysis.profiles import ManufacturingProfile
from via_pcb.models import PCBDesign

VERSION = "1.0.0"


def is_rectangular(design: PCBDesign) -> bool:
    o = design.outline
    return bool(o.closed and o.bbox and o.area and abs(o.area - o.bbox.width * o.bbox.height) < 1e-3 * o.area)


def content_box(design: PCBDesign) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for c in design.components:
        e = extent(c)
        if e:
            xs += [e.min_x, e.max_x]
            ys += [e.min_y, e.max_y]
    for t in design.tracks:
        xs += [t.start.x - t.width / 2, t.end.x - t.width / 2, t.start.x + t.width / 2, t.end.x + t.width / 2]
        ys += [t.start.y - t.width / 2, t.end.y - t.width / 2, t.start.y + t.width / 2, t.end.y + t.width / 2]
    for v in design.vias:
        xs += [v.position.x - v.diameter / 2, v.position.x + v.diameter / 2]
        ys += [v.position.y - v.diameter / 2, v.position.y + v.diameter / 2]
    for z in design.zones:
        xs += [p.x for p in z.outline]
        ys += [p.y for p in z.outline]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def outline_fit(design: PCBDesign, cons: Constraints, profile: ManufacturingProfile) -> tuple[list[Change], str | None]:
    """Returns (changes, reason-if-none)."""
    if cons.outline_fixed:
        return [], "The outline is fixed by the constraints."
    if not is_rectangular(design):
        return [], "Only rectangular outlines are resized automatically."
    box = content_box(design)
    ob = design.outline.bbox
    if box is None or ob is None:
        return [], "Nothing to fit."
    margin = max(cons.edge_margin_mm, profile.min_copper_to_edge)
    new = (
        max(ob.min_x, box[0] - margin),
        max(ob.min_y, box[1] - margin),
        min(ob.max_x, box[2] + margin),
        min(ob.max_y, box[3] + margin),
    )
    new = (round(new[0], 3), round(new[1], 3), round(new[2], 3), round(new[3], 3))
    old_area = ob.width * ob.height
    new_area = (new[2] - new[0]) * (new[3] - new[1])
    if new_area >= old_area * 0.99:
        return [], "The outline already fits the content (less than 1% to gain)."
    return [Change(
        kind=ChangeKind.SET_OUTLINE_RECT, target=Target(kind="outline", id="Edge.Cuts", label="Board outline"),
        before={"min_x": ob.min_x, "min_y": ob.min_y, "max_x": ob.max_x, "max_y": ob.max_y},
        after={"min_x": new[0], "min_y": new[1], "max_x": new[2], "max_y": new[3]},
        reason=f"Fit the outline to the content with a {margin:g} mm margin ({old_area:.0f} -> {new_area:.0f} mm²).",
    )], None  # fmt: skip
