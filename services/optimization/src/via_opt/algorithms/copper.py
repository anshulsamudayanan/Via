# ruff: noqa: E501
"""Manufacturability and thermal: widen tracks and enlarge vias, only where clearance allows."""

from __future__ import annotations

import math
from typing import Any

from via_opt.changes import Change, ChangeKind, Target
from via_pcb.analysis.checks.routing import _copper_thickness, ipc2221_width_mm
from via_pcb.analysis.context import AnalysisContext
from via_pcb.analysis.profiles import ManufacturingProfile
from via_pcb.analysis.shapes import Shape, core_distance, track_owner, track_shapes, via_layers

VERSION = "1.0.0"
STEP = 0.01  # mm: proposed sizes are rounded down to this grid


def _room(ctx: AnalysisContext, mine: list[Shape], net: str | None, limit: float, search: float) -> float:
    """Largest radius increase keeping ``limit`` clearance to other-net copper on the same layers, and the
    profile's copper-to-edge distance to the board outline (never closer than the item already is)."""
    best = search
    edge_limit = ctx.profile.min_copper_to_edge
    for s in mine:
        for a, b in ctx.edge_segments:
            gap = core_distance(s.core, (a, b)) - s.radius
            if gap < edge_limit + search:
                best = min(best, max(0.0, gap - edge_limit))
    shapes, grid = ctx.shapes, ctx.shape_grid
    own = {s.owner.id for s in mine}
    for s in mine:
        for j in grid.query(s.bbox, search + limit):
            o = shapes[j]
            if o.layer != s.layer or o.owner.id in own or (net is not None and o.net == net):
                continue
            gap = core_distance(s.core, o.core) - s.radius - o.radius
            best = min(best, gap - limit)
    return max(0.0, best)


def widen_tracks(ctx: AnalysisContext, targets: dict[str, float], profile: ManufacturingProfile, reason: str,
                 min_targets: float | None = None) -> list[Change]:  # fmt: skip
    """Widen each track below its target (per net, or ``min_targets`` for any net) as far as clearance allows."""
    changes = []
    for t in ctx.design.tracks:
        target = targets.get(t.net or "", min_targets or 0.0)
        if not t.id or target <= t.width + 1e-6:
            continue
        mine = track_shapes(t, track_owner(t))
        room = _room(ctx, mine, t.net, profile.min_clearance, (target - t.width) / 2)
        new = math.floor((t.width + 2 * room) / STEP + 1e-9) * STEP
        new = min(new, target)
        if new > t.width + STEP / 2:
            changes.append(Change(
                kind=ChangeKind.SET_TRACK_WIDTH, target=Target(kind="track", id=t.id, uuid=t.uuid, label=f"Track on {t.layer} [{t.net or ''}]"),
                before={"width": t.width}, after={"width": round(new, 4)},
                reason=reason.format(net=t.net or "(no net)", target=target, achieved=new),
            ))  # fmt: skip
    return changes


def power_targets(ctx: AnalysisContext, power: dict[str, Any]) -> dict[str, float]:
    """IPC-2221 width per net (outer-layer figure, conservative per layer below) for the user's currents."""
    rise = float(power.get("temperature_rise_c", 10.0))
    out = {}
    outer = {ctx.copper_order[0], ctx.copper_order[-1]} if ctx.copper_order else set()
    for net, amps in power.get("nets", {}).items():
        widths = []
        for layer in {t.layer for t in ctx.design.tracks if t.net == net}:
            thickness, _ = _copper_thickness(ctx, layer, power.get("copper_thickness_mm"))
            if thickness:
                widths.append(ipc2221_width_mm(float(amps), rise, thickness, layer in outer))
        if widths:
            out[net] = max(widths)
    return out


def standardize_vias(ctx: AnalysisContext, profile: ManufacturingProfile) -> tuple[list[Change], list[str]]:
    """Bring vias up to the profile (drill, diameter, annular ring) where clearance allows."""
    changes, blocked = [], []
    order = ctx.copper_order
    for v in ctx.design.vias:
        eps = 1e-6
        fails = (v.drill < profile.min_drill - eps or v.diameter < profile.min_via_diameter - eps
                 or (v.diameter - v.drill) / 2 < profile.min_annular_ring - eps)  # fmt: skip
        if not v.id or not fails:
            continue

        def up(x: float) -> float:
            return round(math.ceil(x / STEP - 1e-9) * STEP, 4)

        drill = v.drill if v.drill >= profile.min_drill - eps else up(profile.min_drill)
        need = max(profile.min_via_diameter, drill + 2 * profile.min_annular_ring)
        dia = v.diameter if v.diameter >= need - eps else up(need)
        from via_pcb.analysis.shapes import via_owner

        mine = [
            Shape(((v.position.x, v.position.y),), v.diameter / 2, layer, v.net, via_owner(v))
            for layer in via_layers(v, order)
        ]
        grow = (dia - v.diameter) / 2
        if _room(ctx, mine, v.net, profile.min_clearance, grow + 0.01) + 1e-6 < grow:
            blocked.append(v.id)
            continue
        changes.append(Change(
            kind=ChangeKind.SET_VIA_SIZE, target=Target(kind="via", id=v.id, uuid=v.uuid, label=f"Via [{v.net or ''}]"),
            before={"diameter": v.diameter, "drill": v.drill}, after={"diameter": dia, "drill": drill},
            reason=f"Meet {profile.name}: drill >= {profile.min_drill:g}, diameter >= {profile.min_via_diameter:g}, ring >= {profile.min_annular_ring:g} mm.",
        ))  # fmt: skip
    return changes, blocked
