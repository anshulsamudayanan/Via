# ruff: noqa: E501
"""Placement improvement: a descent pass followed by seeded simulated annealing on the ratsnest.

Cost: the minimum spanning tree of each net's pad positions (the same measure as the ``ratsnest_mm`` metric).
Nets with more than ``MAX_NET_PADS`` pads (power and ground, usually poured) are left out of the *search* for
speed; the reported before/after ratsnest includes them.

Moves are shifts and quarter-turn rotations of unlocked parts. Hard constraints are never traded against cost:
a proposal that leaves the outline margin, comes closer than the component gap to another part, enters a
footprint keep-out or moves a fixed part is rejected outright. A part is either moved or rotated in one candidate
(the change set allows one change per object). Parts on the bottom side are not rotated.

Reproducible: the random generator is seeded with ``SEED`` and parts are visited in a fixed order, so the same design
and constraints always give the same result. The iteration count is fixed; a wall-clock cap exists only as a safety
net, and when it ends the search early the result says so (``budget_exhausted``).
"""

from __future__ import annotations

import math
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from via_opt.changes import Change, ChangeKind, Target
from via_opt.constraints import Constraints, is_fixed, keepout_polygons, overlaps
from via_pcb import geometry as geo
from via_pcb.analysis.checks.placement import extent
from via_pcb.analysis.checks.routing import mst_length
from via_pcb.analysis.shapes import point_in_polygon
from via_pcb.models import BoundingBox, Component, PCBDesign, Side

VERSION = "2.0.0"
SEED = 20260128
FRACTIONS = (1.0, 0.75, 0.5, 0.25)
MAX_COMPONENTS = 1500
MAX_NET_PADS = 40
MAX_ITERATIONS = 20_000
ITERATIONS_PER_PART = 300
TIME_CAP_SECONDS = 20.0
TURNS = (90, 180, 270)
TOL = 1e-3


@dataclass
class PlacementResult:
    changes: list[Change]
    before: float
    after: float
    execution: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Part:
    comp: Component
    cid: str
    origin: tuple[float, float]
    rel_pads: list[tuple[str | None, tuple[float, float]]]  # (net, pad position relative to the origin)
    rel_box: tuple[float, float, float, float]  # extent relative to the origin
    nets: set[str]
    can_turn: bool


def _full_ratsnest(design: PCBDesign, state: dict[str, tuple[float, float, int]]) -> float:
    pts: dict[str, set[tuple[float, float]]] = defaultdict(set)
    for c in design.components:
        dx, dy, k = state.get(c.id or "", (0.0, 0.0, 0))
        for p in c.pads:
            if p.net:
                if k:
                    rx, ry = geo.to_board(
                        (p.position.x - c.position.x, p.position.y - c.position.y), (0.0, 0.0), 90 * k
                    )
                    pts[p.net].add((c.position.x + dx + rx, c.position.y + dy + ry))
                else:
                    pts[p.net].add((p.position.x + dx, p.position.y + dy))
    return sum(mst_length(sorted(v)) for v in pts.values() if len(v) > 1)


def _box_at(part: _Part, dx: float, dy: float, k: int) -> BoundingBox:
    x0, y0, x1, y1 = part.rel_box
    if k:
        corners = [geo.to_board(p, (0.0, 0.0), 90 * k) for p in ((x0, y0), (x0, y1), (x1, y0), (x1, y1))]
        x0, x1 = min(c[0] for c in corners), max(c[0] for c in corners)
        y0, y1 = min(c[1] for c in corners), max(c[1] for c in corners)
    ox, oy = part.origin[0] + dx, part.origin[1] + dy
    return BoundingBox(min_x=ox + x0, min_y=oy + y0, max_x=ox + x1, max_y=oy + y1)


def _pad_points(part: _Part, dx: float, dy: float, k: int) -> list[tuple[str, tuple[float, float]]]:
    out = []
    for net, (rx, ry) in part.rel_pads:
        if net:
            if k:
                rx, ry = geo.to_board((rx, ry), (0.0, 0.0), 90 * k)
            out.append((net, (part.origin[0] + dx + rx, part.origin[1] + dy + ry)))
    return out


class _Grid:
    """Uniform grid of part boxes for near-neighbour overlap queries."""

    def __init__(self, cell: float) -> None:
        self.cell = cell
        self.cells: dict[tuple[int, int], list[str]] = defaultdict(list)
        self.boxes: dict[str, BoundingBox] = {}

    def _keys(self, b: BoundingBox, pad: float) -> list[tuple[int, int]]:
        c = self.cell
        return [
            (i, j)
            for i in range(math.floor((b.min_x - pad) / c), math.floor((b.max_x + pad) / c) + 1)
            for j in range(math.floor((b.min_y - pad) / c), math.floor((b.max_y + pad) / c) + 1)
        ]

    def put(self, cid: str, b: BoundingBox) -> None:
        self.remove(cid)
        self.boxes[cid] = b
        for k in self._keys(b, 0.0):
            self.cells[k].append(cid)

    def remove(self, cid: str) -> None:
        old = self.boxes.pop(cid, None)
        if old is not None:
            for k in self._keys(old, 0.0):
                self.cells[k].remove(cid)

    def clashes(self, cid: str, b: BoundingBox, gap: float) -> bool:
        seen: set[str] = set()
        for k in self._keys(b, gap):
            for o in self.cells.get(k, ()):
                if o != cid and o not in seen:
                    seen.add(o)
                    if overlaps(b, self.boxes[o], gap):
                        return True
        return False


def improve_placement(design: PCBDesign, cons: Constraints) -> PlacementResult:
    ob = design.outline.bbox
    zero = PlacementResult([], 0.0, 0.0, {})
    if ob is None:
        return zero
    margin = cons.edge_margin_mm
    parts: dict[str, _Part] = {}
    for c in design.components:
        e = extent(c)
        if c.id and e is not None:
            ox, oy = c.position.x, c.position.y
            parts[c.id] = _Part(
                comp=c, cid=c.id, origin=(ox, oy),
                rel_pads=[(p.net, (p.position.x - ox, p.position.y - oy)) for p in c.pads],
                rel_box=(e.min_x - ox, e.min_y - oy, e.max_x - ox, e.max_y - oy),
                nets={p.net for p in c.pads if p.net}, can_turn=cons.allow_rotation and c.side == Side.TOP,
            )  # fmt: skip
    movable = [p for p in parts.values() if not is_fixed(p.comp, cons) and p.nets][:MAX_COMPONENTS]
    before_total = _full_ratsnest(design, {})
    if not movable:
        return PlacementResult([], before_total, before_total, {"movable_parts": 0})

    # Nets the search works on, and the pad positions of every part that never moves.
    net_pad_count: dict[str, int] = defaultdict(int)
    for p in parts.values():
        for net, _ in p.rel_pads:
            if net:
                net_pad_count[net] += 1
    searched = {n for n, k in net_pad_count.items() if 2 <= k <= MAX_NET_PADS}
    state: dict[str, tuple[float, float, int]] = {}  # id -> (dx, dy, quarter turns); only parts that moved
    by_net: dict[str, list[str]] = defaultdict(list)
    for p in parts.values():
        for n in p.nets & searched:
            by_net[n].append(p.cid)

    def net_cost(net: str, trial: dict[str, tuple[float, float, int]]) -> float:
        pts: set[tuple[float, float]] = set()
        for cid in by_net[net]:
            part = parts[cid]
            dx, dy, k = trial.get(cid, (0.0, 0.0, 0))
            pts.update(pt for n, pt in _pad_points(part, dx, dy, k) if n == net)
        return mst_length(sorted(pts))

    def cost_of(nets: set[str], trial: dict[str, tuple[float, float, int]]) -> float:
        return sum(net_cost(n, trial) for n in nets if n in searched)

    sizes = [max(p.rel_box[2] - p.rel_box[0], p.rel_box[3] - p.rel_box[1]) for p in parts.values()]
    grid = _Grid(max(1.0, 2 * max(sizes, default=1.0)))
    for p in parts.values():
        grid.put(p.cid, _box_at(p, 0.0, 0.0, 0))
    keepouts = keepout_polygons(design)

    def allowed(part: _Part, dx: float, dy: float, k: int) -> bool:
        b = _box_at(part, dx, dy, k)
        if (
            b.min_x < ob.min_x + margin
            or b.min_y < ob.min_y + margin
            or b.max_x > ob.max_x - margin
            or b.max_y > ob.max_y - margin
        ):
            return False
        if grid.clashes(part.cid, b, cons.component_gap_mm):
            return False
        centre = (part.origin[0] + dx, part.origin[1] + dy)
        return not any(point_in_polygon(centre, poly) for poly in keepouts)

    def apply_state(part: _Part, new: tuple[float, float, int]) -> None:
        if new == (0.0, 0.0, 0):
            state.pop(part.cid, None)
        else:
            state[part.cid] = new
        grid.put(part.cid, _box_at(part, *new))

    def target_shift(part: _Part, st: tuple[float, float, int]) -> tuple[float, float] | None:
        """Vector from the part's connected pads' centroid to where its own pads are now (towards what it connects to)."""
        own = _pad_points(part, *st)
        others = []
        for n in part.nets & searched:
            for cid in by_net[n]:
                if cid != part.cid:
                    others += [pt for nn, pt in _pad_points(parts[cid], *state.get(cid, (0.0, 0.0, 0))) if nn == n]
        mine = [pt for n, pt in own if n in searched]
        if not others or not mine:
            return None
        return (
            sum(q[0] for q in others) / len(others) - sum(q[0] for q in mine) / len(mine),
            sum(q[1] for q in others) / len(others) - sum(q[1] for q in mine) / len(mine),
        )

    total = sum(net_cost(n, state) for n in searched)
    start_total = total
    # Phase 1: descent. Each part tries moving towards what it connects to (100/75/50/25 %).
    for part in movable:
        cur = state.get(part.cid, (0.0, 0.0, 0))
        if cur[2]:
            continue
        shift = target_shift(part, cur)
        if shift is None:
            continue
        nets = part.nets & searched
        base = cost_of(nets, state)
        for f in FRACTIONS:
            new = (cur[0] + shift[0] * f, cur[1] + shift[1] * f, 0)
            if not allowed(part, *new):
                continue
            trial = {**state, part.cid: new}
            c_new = cost_of(nets, trial)
            if c_new < base - 1e-6:
                total += c_new - base
                apply_state(part, new)
                break
    descent_total = total

    # Phase 2: seeded simulated annealing from the descent result; the best state seen is returned.
    rng = random.Random(SEED)  # noqa: S311 - reproducible search, not security
    iterations = min(MAX_ITERATIONS, ITERATIONS_PER_PART * len(movable))
    t0 = max(0.5, 0.02 * total / math.sqrt(len(movable) + 1))
    t_end = 0.001
    reach = max(0.5, 0.2 * min(ob.width, ob.height))
    best, best_total = dict(state), total
    accepted = 0
    started = time.perf_counter()
    done = 0
    exhausted = False
    for i in range(iterations):
        if i % 256 == 0 and time.perf_counter() - started > TIME_CAP_SECONDS:
            exhausted = True
            break
        done = i + 1
        progress = i / iterations
        temp = t0 * (t_end / t0) ** progress
        part = movable[rng.randrange(len(movable))]
        cur = state.get(part.cid, (0.0, 0.0, 0))
        nets = part.nets & searched
        if not nets:
            continue
        roll = rng.random()
        if roll < 0.15 and part.can_turn and cur[0] == 0.0 and cur[1] == 0.0:
            new = (0.0, 0.0, (cur[2] + TURNS.index(rng.choice(TURNS)) + 1) % 4)
        elif cur[2]:
            continue  # a turned part isn't also moved
        elif roll < 0.55 and (shift := target_shift(part, cur)) is not None:
            f = rng.uniform(0.1, 1.0)
            new = (cur[0] + shift[0] * f, cur[1] + shift[1] * f, 0)
        else:
            r = reach * (1 - progress) + 0.1
            new = (cur[0] + rng.uniform(-r, r), cur[1] + rng.uniform(-r, r), 0)
        if new == cur or not allowed(part, *new):
            continue
        base = cost_of(nets, state)
        delta = cost_of(nets, {**state, part.cid: new}) - base
        if delta <= 0 or rng.random() < math.exp(-delta / temp):
            apply_state(part, new)
            total += delta
            accepted += 1
            if total < best_total - 1e-9:
                best, best_total = dict(state), total
    final = best if best_total < start_total - 1e-6 else {}
    execution = {
        "seed": SEED, "algorithm": "descent + simulated annealing", "iterations": done, "iteration_budget": iterations,
        "accepted_moves": accepted, "movable_parts": len(movable), "searched_nets": len(searched),
        "ignored_large_nets": sum(1 for k in net_pad_count.values() if k > MAX_NET_PADS),
        "descent_gain_mm": round(start_total - descent_total, 3), "anneal_gain_mm": round(descent_total - best_total, 3),
        "budget_exhausted": exhausted, "rotation_allowed": cons.allow_rotation,
    }  # fmt: skip
    changes = []
    for c in design.components:
        dx, dy, k = final.get(c.id or "", (0.0, 0.0, 0))
        target = Target(kind="component", id=c.id or "", uuid=c.uuid, label=c.reference)
        if k:
            changes.append(Change(kind=ChangeKind.ROTATE_COMPONENT, target=target, before={"rotation": c.rotation},
                                  after={"rotation": (c.rotation + 90 * k) % 360},
                                  reason="Rotate to shorten unrouted connections."))  # fmt: skip
        elif abs(dx) > 1e-3 or abs(dy) > 1e-3:
            changes.append(Change(kind=ChangeKind.MOVE_COMPONENT, target=target, before={"x": c.position.x, "y": c.position.y},
                                  after={"x": round(c.position.x + dx, 3), "y": round(c.position.y + dy, 3)},
                                  reason="Move towards the parts it connects to, shortening unrouted connections."))  # fmt: skip
    after_total = _full_ratsnest(design, final) if changes else before_total
    return PlacementResult(changes, before_total, after_total, execution)
