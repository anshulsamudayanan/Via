"""Placement improvement: greedy local search that shortens the ratsnest (unrouted connection length).

Moves keep every component inside the outline (with the edge margin), clear of other components'
extents and of footprint keep-outs, and never move fixed parts. Moving routed parts breaks their
tracks, so such candidates are marked "requires re-routing" by validation. Deterministic (no randomness).
"""

from __future__ import annotations

from collections import defaultdict

from via_opt.changes import Change, ChangeKind, Target
from via_opt.constraints import Constraints, is_fixed, keepout_polygons, overlaps
from via_pcb.analysis.checks.placement import extent
from via_pcb.analysis.checks.routing import mst_length
from via_pcb.analysis.shapes import point_in_polygon
from via_pcb.models import BoundingBox, PCBDesign

VERSION = "1.0.0"
FRACTIONS = (1.0, 0.75, 0.5, 0.25)
MAX_COMPONENTS = 300
PASSES = 2


def _net_points(design: PCBDesign, offsets: dict[str, tuple[float, float]]) -> dict[str, list[tuple[float, float]]]:
    out: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for c in design.components:
        dx, dy = offsets.get(c.id or "", (0.0, 0.0))
        for p in c.pads:
            if p.net:
                out[p.net].append((p.position.x + dx, p.position.y + dy))
    return out


def improve_placement(design: PCBDesign, cons: Constraints) -> tuple[list[Change], float, float]:
    """Returns (changes, ratsnest before, ratsnest after)."""
    ob = design.outline.bbox
    if ob is None:
        return [], 0.0, 0.0
    m = cons.edge_margin_mm
    boxes: dict[str, BoundingBox] = {c.id: e for c in design.components if c.id and (e := extent(c)) is not None}
    movable = [c for c in design.components if c.id and not is_fixed(c, cons) and c.id in boxes][:MAX_COMPONENTS]
    keepouts = keepout_polygons(design)
    offsets: dict[str, tuple[float, float]] = {}
    nets_of = {c.id: {p.net for p in c.pads if p.net} for c in design.components if c.id}

    def cost(net_pts: dict[str, list[tuple[float, float]]], nets: set[str]) -> float:
        return sum(mst_length(sorted(set(net_pts[n]))) for n in nets if len(net_pts[n]) > 1)

    before_total = sum(mst_length(sorted(set(p))) for p in _net_points(design, {}).values() if len(p) > 1)
    for _ in range(PASSES):
        for c in movable:
            cid = c.id or ""
            nets = nets_of[cid]
            if not nets:
                continue
            pts = _net_points(design, offsets)
            ox, oy = offsets.get(cid, (0.0, 0.0))
            others = [q for n in nets for q in pts[n]]
            mine = [(p.position.x + ox, p.position.y + oy) for p in c.pads if p.net]
            if not others or not mine:
                continue
            tx = sum(q[0] for q in others) / len(others) - sum(q[0] for q in mine) / len(mine)
            ty = sum(q[1] for q in others) / len(others) - sum(q[1] for q in mine) / len(mine)
            base = cost(pts, nets)
            for f in FRACTIONS:
                nx, ny = ox + tx * f, oy + ty * f
                b = boxes[cid]
                moved = BoundingBox(min_x=b.min_x + nx, min_y=b.min_y + ny, max_x=b.max_x + nx, max_y=b.max_y + ny)
                if (
                    moved.min_x < ob.min_x + m
                    or moved.min_y < ob.min_y + m
                    or moved.max_x > ob.max_x - m
                    or moved.max_y > ob.max_y - m
                ):
                    continue
                if any(
                    overlaps(moved, _shift(boxes[o], offsets.get(o)), cons.component_gap_mm) for o in boxes if o != c.id
                ):
                    continue
                centre = (c.position.x + nx, c.position.y + ny)
                if any(point_in_polygon(centre, poly) for poly in keepouts):
                    continue
                trial = dict(offsets)
                trial[cid] = (nx, ny)
                if cost(_net_points(design, trial), nets) < base - 1e-6:
                    offsets = trial
                    break
    changes = [
        Change(kind=ChangeKind.MOVE_COMPONENT,
               target=Target(kind="component", id=c.id or "", uuid=c.uuid, label=c.reference),
               before={"x": c.position.x, "y": c.position.y},
               after={"x": round(c.position.x + offsets[c.id][0], 3), "y": round(c.position.y + offsets[c.id][1], 3)},
               reason="Move towards the parts it connects to, shortening unrouted connections.")
        for c in design.components if c.id in offsets and (abs(offsets[c.id][0]) > 1e-3 or abs(offsets[c.id][1]) > 1e-3)
    ]  # fmt: skip
    after_total = sum(mst_length(sorted(set(p))) for p in _net_points(design, offsets).values() if len(p) > 1)
    return changes, before_total, after_total


def _shift(b: BoundingBox, off: tuple[float, float] | None) -> BoundingBox:
    if not off:
        return b
    return BoundingBox(min_x=b.min_x + off[0], min_y=b.min_y + off[1], max_x=b.max_x + off[0], max_y=b.max_y + off[1])
