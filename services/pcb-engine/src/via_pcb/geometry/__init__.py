"""Planar geometry helpers used by adapters and analyses.

Pure functions on ``(x, y)`` tuples so they are cheap, easy to test and free of
model dependencies. Angles are degrees. Rotation follows the EDA convention for
a Y-down coordinate system: a positive angle is counter-clockwise *on screen*.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

Vec = tuple[float, float]

EPSILON = 1e-3  # mm; endpoint-matching tolerance for outline assembly


def rotate(p: Vec, angle_deg: float) -> Vec:
    """Rotate ``p`` about the origin, CCW on a Y-down screen."""
    if not angle_deg:
        return p
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    x, y = p
    return (x * c + y * s, -x * s + y * c)


def to_board(local: Vec, origin: Vec, angle_deg: float) -> Vec:
    """Map a footprint-local point to board coordinates."""
    rx, ry = rotate(local, angle_deg)
    return (origin[0] + rx, origin[1] + ry)


def distance(a: Vec, b: Vec) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def circle_through(a: Vec, b: Vec, c: Vec) -> tuple[Vec, float] | None:
    """Centre and radius of the circle through three points (None if collinear)."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy), distance((ux, uy), a)


def _arc_sweep(start: Vec, mid: Vec, end: Vec) -> tuple[Vec, float, float, float] | None:
    """Return (centre, radius, start_angle, signed_sweep) in radians, math orientation."""
    circ = circle_through(start, mid, end)
    if circ is None:
        return None
    (cx, cy), r = circ
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    am = math.atan2(mid[1] - cy, mid[0] - cx)
    a1 = math.atan2(end[1] - cy, end[0] - cx)

    def ccw(frm: float, to: float) -> float:
        return (to - frm) % (2 * math.pi)

    sweep = ccw(a0, a1)
    if ccw(a0, am) > sweep:  # mid not on the CCW path -> go clockwise
        sweep -= 2 * math.pi
    return (cx, cy), r, a0, sweep


def arc_length(start: Vec, mid: Vec, end: Vec) -> float:
    s = _arc_sweep(start, mid, end)
    if s is None:
        return distance(start, end)
    _, r, _, sweep = s
    return abs(sweep) * r


def arc_mid_from_center(start: Vec, center: Vec, angle_deg: float) -> tuple[Vec, Vec]:
    """Convert a legacy (start, centre, angle) arc to (mid, end) points.

    Legacy KiCad stores ``start`` as the centre and ``end`` as the arc start; the
    sweep angle is CW-positive on screen, which is CCW-positive in math terms
    once Y is flipped -> we can rotate with :func:`rotate` using ``-angle``.
    """
    rel = (start[0] - center[0], start[1] - center[1])
    m = rotate(rel, -angle_deg / 2)
    e = rotate(rel, -angle_deg)
    return (center[0] + m[0], center[1] + m[1]), (center[0] + e[0], center[1] + e[1])


def sample_arc(start: Vec, mid: Vec, end: Vec, max_step_deg: float = 10.0) -> list[Vec]:
    """Polyline approximation of an arc, including both endpoints."""
    s = _arc_sweep(start, mid, end)
    if s is None:
        return [start, end]
    (cx, cy), r, a0, sweep = s
    steps = max(2, math.ceil(abs(math.degrees(sweep)) / max_step_deg))
    pts = [
        (cx + r * math.cos(a0 + sweep * i / steps), cy + r * math.sin(a0 + sweep * i / steps)) for i in range(steps + 1)
    ]
    pts[0], pts[-1] = start, end
    return pts


def sample_circle(center: Vec, radius: float, steps: int = 36) -> list[Vec]:
    return [
        (center[0] + radius * math.cos(2 * math.pi * i / steps), center[1] + radius * math.sin(2 * math.pi * i / steps))
        for i in range(steps)
    ]


def polygon_area(points: Sequence[Vec]) -> float:
    """Unsigned shoelace area."""
    n = len(points)
    if n < 3:
        return 0.0
    acc = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        acc += x1 * y2 - x2 * y1
    return abs(acc) / 2.0


def polyline_length(points: Sequence[Vec]) -> float:
    return sum(distance(points[i], points[i + 1]) for i in range(len(points) - 1))


@dataclass
class BBox:
    min_x: float = math.inf
    min_y: float = math.inf
    max_x: float = -math.inf
    max_y: float = -math.inf

    def add(self, p: Vec, pad: float = 0.0) -> None:
        self.min_x = min(self.min_x, p[0] - pad)
        self.min_y = min(self.min_y, p[1] - pad)
        self.max_x = max(self.max_x, p[0] + pad)
        self.max_y = max(self.max_y, p[1] + pad)

    def extend(self, pts: Iterable[Vec], pad: float = 0.0) -> None:
        for p in pts:
            self.add(p, pad)

    @property
    def empty(self) -> bool:
        return self.min_x > self.max_x

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.min_x, self.min_y, self.max_x, self.max_y)


@dataclass
class OutlineEdge:
    """One outline primitive flattened to a polyline (open) or a ring (closed)."""

    points: list[Vec]
    closed: bool = False


@dataclass
class OutlineResult:
    loops: list[list[Vec]] = field(default_factory=list)
    open_chains: int = 0

    @property
    def closed(self) -> bool:
        return bool(self.loops) and self.open_chains == 0

    @property
    def area(self) -> float | None:
        """Area of the largest loop minus the other loops (treated as cut-outs)."""
        if not self.loops:
            return None
        areas = sorted((polygon_area(loop) for loop in self.loops), reverse=True)
        return max(0.0, areas[0] - sum(areas[1:]))


def _close(a: Vec, b: Vec, tol: float) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def assemble_outline(edges: Sequence[OutlineEdge], tol: float = EPSILON) -> OutlineResult:
    """Chain outline primitives into closed loops.

    Already-closed primitives (circles, rectangles, polygons) become loops
    directly. Open primitives are chained end-to-end (in either direction);
    chains that do not close are counted in ``open_chains``.
    """
    result = OutlineResult()
    pending: list[list[Vec]] = []
    for e in edges:
        if len(e.points) < 2:
            continue
        if e.closed:
            result.loops.append(list(e.points))
        else:
            pending.append(list(e.points))

    while pending:
        chain = pending.pop()
        progress = True
        while progress and not _close(chain[0], chain[-1], tol):
            progress = False
            for i, seg in enumerate(pending):
                if _close(chain[-1], seg[0], tol):
                    chain.extend(seg[1:])
                elif _close(chain[-1], seg[-1], tol):
                    chain.extend(reversed(seg[:-1]))
                elif _close(chain[0], seg[-1], tol):
                    chain[:0] = seg[:-1]
                elif _close(chain[0], seg[0], tol):
                    chain[:0] = list(reversed(seg[1:]))
                else:
                    continue
                pending.pop(i)
                progress = True
                break
        if len(chain) > 2 and _close(chain[0], chain[-1], tol):
            result.loops.append(chain[:-1])
        else:
            result.open_chains += 1
    return result


__all__ = [
    "EPSILON",
    "BBox",
    "OutlineEdge",
    "OutlineResult",
    "Vec",
    "arc_length",
    "arc_mid_from_center",
    "assemble_outline",
    "circle_through",
    "distance",
    "polygon_area",
    "polyline_length",
    "rotate",
    "sample_arc",
    "sample_circle",
    "to_board",
]
