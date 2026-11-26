"""Exact 2D copper geometry for analysis: shapes, distances and a spatial grid.

Every copper item becomes a :class:`Shape` = a *core* (a point, a segment or a convex polygon)
inflated by a *radius*. Distances between shapes are then ``core distance - r1 - r2``, which is
exact for:

* round pads and vias (point + radius);
* oval pads (segment + radius, a stadium);
* rectangular pads (polygon, radius 0);
* rounded-rectangle pads (the rectangle shrunk by the corner radius, inflated by it: exact);
* tracks (segment + half width); arc tracks are split into chords whose sagitta is at most
  ``ARC_TOLERANCE`` (2 µm).

Trapezoid, chamfered and custom pads use their bounding rectangle and are flagged ``approx``
(custom pad primitives aren't in the normalized model). Zones are not shapes here: their filled
copper isn't stored (see docs/PCB_ANALYSIS.md).
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field

from via_pcb import geometry as geo
from via_pcb.models import Component, Graphic, Pad, PadType, PCBDesign, Track, Via

Vec = tuple[float, float]
#: Maximum chord sagitta when sampling arcs (mm).
ARC_TOLERANCE = 0.002


@dataclass(frozen=True, slots=True)
class Owner:
    kind: str  # component | pad | track | via
    id: str
    label: str
    component: str | None = None  # reference designator, for pads
    pad_number: str | None = None


@dataclass(slots=True)
class Shape:
    core: tuple[Vec, ...]
    radius: float
    layer: str
    net: str | None
    owner: Owner
    approx: bool = False
    bbox: tuple[float, float, float, float] = field(init=False)

    def __post_init__(self) -> None:
        xs = [p[0] for p in self.core]
        ys = [p[1] for p in self.core]
        r = self.radius
        self.bbox = (min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r)


@dataclass(frozen=True, slots=True)
class Hole:
    core: tuple[Vec, ...]  # point (round) or segment (slot)
    radius: float
    owner: Owner
    plated: bool


# --- distances ---------------------------------------------------------------------------------


def point_segment_distance(p: Vec, a: Vec, b: Vec) -> float:
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length2 = dx * dx + dy * dy
    if length2 == 0.0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def _orient(a: Vec, b: Vec, c: Vec) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(a: Vec, b: Vec, c: Vec, d: Vec) -> bool:
    d1, d2 = _orient(c, d, a), _orient(c, d, b)
    d3, d4 = _orient(a, b, c), _orient(a, b, d)
    # Proper crossing; touching and collinear cases are found by the endpoint distances.
    return d1 * d2 < 0 and d3 * d4 < 0


def segment_segment_distance(a: Vec, b: Vec, c: Vec, d: Vec) -> float:
    if segments_intersect(a, b, c, d):
        return 0.0
    return min(
        point_segment_distance(a, c, d),
        point_segment_distance(b, c, d),
        point_segment_distance(c, a, b),
        point_segment_distance(d, a, b),
    )


def point_in_convex_polygon(p: Vec, poly: Sequence[Vec]) -> bool:
    sign = 0
    n = len(poly)
    for i in range(n):
        o = _orient(poly[i], poly[(i + 1) % n], p)
        if o != 0:
            s = 1 if o > 0 else -1
            if sign == 0:
                sign = s
            elif s != sign:
                return False
    return True


def point_in_polygon(p: Vec, poly: Sequence[Vec]) -> bool:
    """Ray casting; any simple polygon (e.g. zone outlines)."""
    x, y = p
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _edges(core: Sequence[Vec]) -> Iterator[tuple[Vec, Vec]]:
    if len(core) == 1:
        yield core[0], core[0]
    elif len(core) == 2:
        yield core[0], core[1]
    else:
        for i in range(len(core)):
            yield core[i], core[(i + 1) % len(core)]


def core_distance(a: Sequence[Vec], b: Sequence[Vec]) -> float:
    if len(a) >= 3 and any(point_in_convex_polygon(p, a) for p in b):
        return 0.0
    if len(b) >= 3 and any(point_in_convex_polygon(p, b) for p in a):
        return 0.0
    return min(segment_segment_distance(p, q, r, s) for p, q in _edges(a) for r, s in _edges(b))


def distance(a: Shape, b: Shape) -> float:
    """Edge-to-edge distance between two copper shapes (0 when touching or overlapping)."""
    return max(0.0, core_distance(a.core, b.core) - a.radius - b.radius)


def closest_points(a: Sequence[Vec], b: Sequence[Vec]) -> Vec:
    """A point roughly midway between two cores at their closest approach (for markers)."""
    best = (math.inf, a[0])
    for p in a:
        for r, s in _edges(b):
            d = point_segment_distance(p, r, s)
            if d < best[0]:
                best = (d, p)
    for p in b:
        for r, s in _edges(a):
            d = point_segment_distance(p, r, s)
            if d < best[0]:
                best = (d, p)
    return best[1]


# --- building shapes from the design ------------------------------------------------------------


def copper_order(design: PCBDesign) -> list[str]:
    """Copper layers from top to bottom: F.Cu, In1.Cu ... InN.Cu, B.Cu (by name; KiCad 9 renumbered ordinals)."""
    names = [layer.name for layer in design.layers if layer.kind == "copper"]

    def key(name: str) -> tuple[int, int]:
        if name == "F.Cu":
            return (0, 0)
        if name == "B.Cu":
            return (2, 0)
        m = re.match(r"In(\d+)\.Cu$", name)
        return (1, int(m.group(1))) if m else (1, 10_000)

    return sorted(names, key=key)


def via_layers(via: Via, order: list[str]) -> list[str]:
    """All copper layers a via has copper on: every layer between its two end layers."""
    ends = [layer for layer in via.layers if layer in order]
    if len(ends) < 2:
        return ends
    i, j = sorted(order.index(layer) for layer in ends[:2])
    return order[i : j + 1]


def _rect(cx: float, cy: float, w: float, h: float, angle: float) -> tuple[Vec, ...]:
    corners = ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))
    return tuple(geo.to_board(c, (cx, cy), angle) for c in corners)


def pad_core(pad: Pad) -> tuple[tuple[Vec, ...], float, bool]:
    """(core, radius, approximate?) of a pad's copper outline."""
    cx, cy = pad.position.x, pad.position.y
    w, h = pad.size.x, pad.size.y
    shape = pad.shape
    if shape == "circle":
        return ((cx, cy),), w / 2, False
    if shape == "oval":
        long_, short = max(w, h), min(w, h)
        half = (long_ - short) / 2
        local = ((-half, 0.0), (half, 0.0)) if w >= h else ((0.0, -half), (0.0, half))
        core = tuple(geo.to_board(p, (cx, cy), pad.rotation) for p in local)
        return (core if half > 0 else ((cx, cy),)), short / 2, False
    if shape == "rect":
        return _rect(cx, cy, w, h, pad.rotation), 0.0, False
    if shape == "roundrect" and pad.roundrect_ratio is not None:
        r = max(0.0, min(pad.roundrect_ratio, 0.5)) * min(w, h)
        iw, ih = w - 2 * r, h - 2 * r
        if iw <= 1e-9 and ih <= 1e-9:
            return ((cx, cy),), r, False
        if iw <= 1e-9 or ih <= 1e-9:
            half = max(iw, ih) / 2
            local = ((-half, 0.0), (half, 0.0)) if iw > ih else ((0.0, -half), (0.0, half))
            return tuple(geo.to_board(p, (cx, cy), pad.rotation) for p in local), r, False
        return _rect(cx, cy, iw, ih, pad.rotation), r, False
    # trapezoid, chamfered_rect, custom, roundrect without ratio: bounding rectangle.
    return _rect(cx, cy, w, h, pad.rotation), 0.0, True


def arc_chords(start: Vec, mid: Vec, end: Vec) -> list[Vec]:
    circle = geo.circle_through(start, mid, end)
    if circle is None:
        return [start, end]
    _, radius = circle
    ratio = max(-1.0, min(1.0, 1.0 - ARC_TOLERANCE / radius))
    step = max(0.5, min(10.0, math.degrees(2 * math.acos(ratio))))
    return geo.sample_arc(start, mid, end, max_step_deg=step)


def track_shapes(track: Track, owner: Owner) -> list[Shape]:
    r = track.width / 2
    a, b = (track.start.x, track.start.y), (track.end.x, track.end.y)
    if track.kind == "arc" and track.mid is not None:
        pts = arc_chords(a, (track.mid.x, track.mid.y), b)
        return [Shape((pts[i], pts[i + 1]), r, track.layer, track.net, owner) for i in range(len(pts) - 1)]
    return [Shape((a, b), r, track.layer, track.net, owner)]


def pad_owner(component: Component, pad: Pad) -> Owner:
    return Owner(
        "pad",
        pad.id or f"{component.reference}/{pad.number}",
        f"{component.reference} pad {pad.number}",
        component=component.reference,
        pad_number=pad.number,
    )


def track_owner(track: Track) -> Owner:
    kind = "Arc track" if track.kind == "arc" else "Track"
    net = f" [{track.net}]" if track.net else ""
    return Owner("track", track.id or "", f"{kind} on {track.layer}{net}")


def via_owner(via: Via) -> Owner:
    return Owner("via", via.id or "", "Via" + (f" [{via.net}]" if via.net else ""))


def copper_shapes(design: PCBDesign) -> list[Shape]:
    order = copper_order(design)
    copper = set(order)
    shapes: list[Shape] = []
    for c in design.components:
        for p in c.pads:
            if p.type == PadType.NPTH:
                continue
            core, radius, approx = pad_core(p)
            owner = pad_owner(c, p)
            for layer in p.layers:
                if layer in copper and (p.size.x > 0 or p.size.y > 0):
                    shapes.append(Shape(core, radius, layer, p.net, owner, approx))
    for t in design.tracks:
        if t.layer in copper and t.width > 0:
            shapes.extend(track_shapes(t, track_owner(t)))
    for v in design.vias:
        owner = via_owner(v)
        for layer in via_layers(v, order):
            shapes.append(Shape(((v.position.x, v.position.y),), v.diameter / 2, layer, v.net, owner))
    return shapes


def holes(design: PCBDesign) -> list[Hole]:
    out: list[Hole] = []
    for c in design.components:
        for p in c.pads:
            if p.drill is None or p.drill.diameter <= 0:
                continue
            cx = p.position.x + (p.drill.offset.x if p.drill.offset else 0.0)
            cy = p.position.y + (p.drill.offset.y if p.drill.offset else 0.0)
            d = p.drill.diameter
            core: tuple[Vec, ...] = ((cx, cy),)
            radius = d / 2
            if p.drill.slot_length:
                long_, short = max(d, p.drill.slot_length), min(d, p.drill.slot_length)
                half = (long_ - short) / 2
                # KiCad (drill oval X Y): X along the pad's local x axis.
                local = ((-half, 0.0), (half, 0.0)) if d >= p.drill.slot_length else ((0.0, -half), (0.0, half))
                core = tuple(geo.to_board(q, (cx, cy), p.rotation) for q in local)
                radius = short / 2
            out.append(Hole(core, radius, pad_owner(c, p), plated=p.type != PadType.NPTH))
    for v in design.vias:
        if v.drill > 0:
            out.append(Hole(((v.position.x, v.position.y),), v.drill / 2, via_owner(v), plated=True))
    return out


def outline_segments(graphics: Iterable[Graphic]) -> list[tuple[Vec, Vec]]:
    """Board edge as segments (arcs and circles sampled within ARC_TOLERANCE)."""
    segs: list[tuple[Vec, Vec]] = []
    for g in graphics:
        p = [(pt.x, pt.y) for pt in g.points]
        if g.kind == "line" and len(p) >= 2:
            segs.append((p[0], p[1]))
        elif g.kind == "arc" and len(p) >= 3:
            pts = arc_chords(p[0], p[1], p[2])
            segs.extend((pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        elif g.kind == "circle" and len(p) >= 2:
            r = geo.distance(p[0], p[1])
            ratio = max(-1.0, min(1.0, 1.0 - ARC_TOLERANCE / r)) if r > 0 else 1.0
            steps = max(12, math.ceil(360 / max(0.5, math.degrees(2 * math.acos(ratio)))))
            pts = geo.sample_circle(p[0], r, steps)
            segs.extend((pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))
        elif g.kind == "rect" and len(p) >= 2:
            (x1, y1), (x2, y2) = p[0], p[1]
            corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
            segs.extend((corners[i], corners[(i + 1) % 4]) for i in range(4))
        elif g.kind == "polygon" and len(p) >= 2:
            segs.extend((p[i], p[(i + 1) % len(p)]) for i in range(len(p)))
    return segs


# --- spatial index -----------------------------------------------------------------------------


class Grid:
    """Uniform grid over bounding boxes; ``query`` returns candidates whose boxes may be within ``margin``."""

    def __init__(self, cell: float = 2.0) -> None:
        self.cell = cell
        self.cells: dict[tuple[int, int], list[int]] = defaultdict(list)

    def _range(self, box: tuple[float, float, float, float]) -> Iterator[tuple[int, int]]:
        c = self.cell
        for i in range(math.floor(box[0] / c), math.floor(box[2] / c) + 1):
            for j in range(math.floor(box[1] / c), math.floor(box[3] / c) + 1):
                yield (i, j)

    def insert(self, index: int, box: tuple[float, float, float, float]) -> None:
        for key in self._range(box):
            self.cells[key].append(index)

    def query(self, box: tuple[float, float, float, float], margin: float = 0.0) -> set[int]:
        grown = (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin)
        out: set[int] = set()
        for key in self._range(grown):
            out.update(self.cells.get(key, ()))
        return out


def boxes_within(a: tuple[float, float, float, float], b: tuple[float, float, float, float], margin: float) -> bool:
    return not (a[2] + margin < b[0] or b[2] + margin < a[0] or a[3] + margin < b[1] or b[3] + margin < a[1])
