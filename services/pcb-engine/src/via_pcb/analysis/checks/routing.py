# ruff: noqa: E501  (user-facing finding texts read better unwrapped)
"""Routing and electrical checks.

* ``routing_detour`` and ``netclass_track_width``: VIA deterministic, measured from the design.
* ``track_current_capacity`` and ``impedance_estimate``: calculated estimates from published
  formulas, run only with user-supplied requirements (``options["power"]``, ``options["impedance"]``);
  VIA never guesses currents or target impedances.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from via_pcb.analysis.context import AnalysisContext
from via_pcb.analysis.findings import (
    Category,
    Evidence,
    Finding,
    ObjectKind,
    ObjectRef,
    Region,
    Severity,
    Verification,
)
from via_pcb.analysis.registry import Check
from via_pcb.models import BoundingBox, Point, Track

MM_PER_MIL = 0.0254


def _region(tracks: list[Track]) -> Region:
    xs = [v for t in tracks for v in (t.start.x, t.end.x)]
    ys = [v for t in tracks for v in (t.start.y, t.end.y)]
    return Region(
        bbox=BoundingBox(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys)),
        points=[Point(x=(t.start.x + t.end.x) / 2, y=(t.start.y + t.end.y) / 2) for t in tracks[:50]],
        layers=sorted({t.layer for t in tracks}),
    )


def _track_refs(tracks: list[Track]) -> list[ObjectRef]:
    return [ObjectRef(kind=ObjectKind.TRACK, id=t.id or "", label=f"Track on {t.layer}") for t in tracks[:100] if t.id]


def mst_length(points: list[tuple[float, float]]) -> float:
    """Euclidean minimum spanning tree length (Prim, O(n²))."""
    if len(points) < 2:
        return 0.0
    inside = [False] * len(points)
    best = [math.inf] * len(points)
    best[0] = 0.0
    total = 0.0
    for _ in points:
        i = min((k for k in range(len(points)) if not inside[k]), key=lambda k: best[k])
        inside[i] = True
        total += best[i]
        for k in range(len(points)):
            if not inside[k]:
                best[k] = min(best[k], math.dist(points[i], points[k]))
    return total


class DetourCheck(Check):
    id = "routing_detour"
    version = "1.0.0"
    category = Category.ROUTING
    title = "Routing detours"
    description = "Nets whose routed track length is much longer than the shortest tree joining their pads."

    RATIO = 2.0
    MIN_MST = 5.0
    MAX_FINDINGS = 20

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        zone_nets = {z.net for z in ctx.design.zones if z.net and not z.keepout}
        pads: dict[str, set[tuple[float, float]]] = defaultdict(set)
        for _, p in ctx.pads_with_component:
            if p.net:
                pads[p.net].add((round(p.position.x, 4), round(p.position.y, 4)))
        tracks: dict[str, list[Track]] = defaultdict(list)
        for t in ctx.design.tracks:
            if t.net:
                tracks[t.net].append(t)
        rows = []
        for net, pts in pads.items():
            if net in zone_nets or len(pts) < 2 or net not in tracks:
                continue
            m = mst_length(sorted(pts))
            routed = sum(t.length for t in tracks[net])
            if m >= self.MIN_MST and routed / m > self.RATIO:
                rows.append((routed / m, net, routed, m))
        for ratio, net, routed, m in sorted(rows, reverse=True)[: self.MAX_FINDINGS]:
            yield Finding(
                check_id=self.id, rule="long_detour", category=self.category, severity=Severity.INFO,
                title=f"{net} is routed {ratio:.1f}x its shortest possible length",
                description=f"Net {net} has {routed:.1f} mm of track; the shortest straight-line tree joining its {len(pads[net])} pads is {m:.1f} mm.",
                explanation="Long detours add resistance, inductance and coupling, and often mean a congested area or a placement that could be improved. Some length is unavoidable (Manhattan routing, obstacles, length matching), so this is a pointer, not a rule.",
                objects=[ObjectRef(kind=ObjectKind.NET, id=net, label=net), *_track_refs(tracks[net])],
                nets=[net], region=_region(tracks[net]), verification=Verification.HEURISTIC, confidence=0.5,
                evidence=[Evidence(kind="measurement", label="Routed length", value=f"{routed:.2f} mm", numeric_value=round(routed, 3), unit="mm"),
                          Evidence(kind="measurement", label="Minimum spanning tree of pads", value=f"{m:.2f} mm", numeric_value=round(m, 3), unit="mm"),
                          Evidence(kind="measurement", label="Ratio", value=f"{ratio:.2f}", numeric_value=round(ratio, 3), expected=f"<= {self.RATIO:g}")],
            ).with_fingerprint(net)  # fmt: skip


class NetClassWidthCheck(Check):
    id = "netclass_track_width"
    version = "1.0.0"
    category = Category.DESIGN_RULES
    title = "Tracks narrower than their net class"
    description = "Tracks narrower than their net class's track width (needs the project's .kicad_pro)."

    def skip_reason(self, ctx: AnalysisContext) -> str | None:
        if ctx.design.constraints.rules_source != "project_file":
            return "Needs the project's net classes; upload the KiCad project as a .zip."
        return None

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        width_of: dict[str, tuple[str, float]] = {}
        for nc in ctx.design.constraints.net_classes:
            if nc.track_width:
                for net in nc.nets:
                    width_of.setdefault(net, (nc.name, nc.track_width))
        narrow: dict[str, list[Track]] = defaultdict(list)
        for t in ctx.design.tracks:
            if t.net in width_of and t.width < width_of[t.net][1] - 1e-6:
                narrow[t.net].append(t)
        for net, ts in sorted(narrow.items()):
            cls, width = width_of[net]
            worst = min(t.width for t in ts)
            yield Finding(
                check_id=self.id, rule="narrower_than_netclass", category=self.category, severity=Severity.LOW,
                title=f"{net}: tracks narrower than net class {cls} ({width:g} mm)",
                description=f"{len(ts)} track segment(s) on {net} are narrower than the {width:g} mm of net class {cls}; the narrowest is {worst:g} mm.",
                explanation="A net class's track width is the designer's intended width (for current or impedance). KiCad uses it as the default, not a minimum, so narrower segments are allowed, often to neck down into fine-pitch pads, but on power nets they can be bottlenecks.",
                objects=[ObjectRef(kind=ObjectKind.NET, id=net, label=net), *_track_refs(ts)],
                nets=[net], region=_region(ts), verification=Verification.HEURISTIC, confidence=0.7,
                evidence=[Evidence(kind="measurement", label="Narrowest track", value=f"{worst:g} mm", numeric_value=worst, unit="mm", expected=f">= {width:g} mm"),
                          Evidence(kind="rule", label=f"Net class {cls} track width", value=f"{width:g} mm", numeric_value=width, unit="mm")],
            ).with_fingerprint(net)  # fmt: skip


def ipc2221_width_mm(current_a: float, temp_rise_c: float, thickness_mm: float, outer: bool) -> float:
    """Minimum track width by IPC-2221: I = k·ΔT^0.44·A^0.725, A in mil², k = 0.048 outer / 0.024 inner."""
    k = 0.048 if outer else 0.024
    area_mil2 = (current_a / (k * temp_rise_c**0.44)) ** (1 / 0.725)
    return area_mil2 / (thickness_mm / MM_PER_MIL) * MM_PER_MIL


def _copper_thickness(ctx: AnalysisContext, layer: str, override: float | None) -> tuple[float | None, str]:
    if ctx.design.stackup is not None:
        for sl in ctx.design.stackup.layers:
            if sl.name == layer and sl.thickness:
                return sl.thickness, "board stackup"
    if override:
        return override, "analysis input"
    return None, ""


class CurrentCapacityCheck(Check):
    id = "track_current_capacity"
    version = "1.0.0"
    category = Category.POWER
    title = "Track current capacity (IPC-2221)"
    description = "Tracks narrower than IPC-2221 requires for the currents you specify per net."

    def skip_reason(self, ctx: AnalysisContext) -> str | None:
        power = ctx.options.get("power")
        if not isinstance(power, dict) or not power.get("nets"):
            return "No current requirements given (analysis option power.nets, amps per net)."
        return None

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        power: dict[str, Any] = ctx.options["power"]
        rise = float(power.get("temperature_rise_c", 10.0))
        override = power.get("copper_thickness_mm")
        outer = {ctx.copper_order[0], ctx.copper_order[-1]} if ctx.copper_order else set()
        missing: list[str] = []
        for net, amps in sorted(power["nets"].items()):
            by_layer: dict[str, list[Track]] = defaultdict(list)
            for t in ctx.design.tracks:
                if t.net == net:
                    by_layer[t.layer].append(t)
            for layer, ts in sorted(by_layer.items()):
                thickness, src = _copper_thickness(ctx, layer, override)
                if thickness is None:
                    missing.append(layer)
                    continue
                need = ipc2221_width_mm(float(amps), rise, thickness, layer in outer)
                narrow = [t for t in ts if t.width < need - 1e-6]
                if not narrow:
                    continue
                worst = min(t.width for t in narrow)
                yield Finding(
                    check_id=self.id, rule="track_too_narrow_for_current", category=self.category, severity=Severity.MEDIUM,
                    title=f"{net} on {layer}: tracks too narrow for {amps:g} A",
                    description=f"IPC-2221 needs {need:.3f} mm for {amps:g} A at a {rise:g} °C rise on {'an outer' if layer in outer else 'an inner'} layer with {thickness * 1000:g} µm copper; {len(narrow)} segment(s) are narrower (narrowest {worst:g} mm).",
                    explanation="Undersized tracks heat up under load and drop voltage. IPC-2221's chart-based formula is conservative and doesn't model nearby planes or airflow (IPC-2152 is more precise), so treat this as a calculated estimate.",
                    objects=[ObjectRef(kind=ObjectKind.NET, id=net, label=net), *_track_refs(narrow)],
                    nets=[net], region=_region(narrow), verification=Verification.HEURISTIC, confidence=0.8,
                    evidence=[Evidence(kind="measurement", label="Narrowest track", value=f"{worst:g} mm", numeric_value=worst, unit="mm", expected=f">= {need:.3f} mm"),
                              Evidence(kind="reference", label="Formula", value="IPC-2221: I = k·ΔT^0.44·A^0.725 (A in mil², k = 0.048 outer, 0.024 inner)"),
                              Evidence(kind="rule", label="Inputs", value=f"{amps:g} A (user), ΔT {rise:g} °C, copper {thickness * 1000:g} µm ({src})")],
                    suggested_resolution=f"Widen the tracks to at least {need:.2f} mm, add parallel copper or use a zone.",
                ).with_fingerprint(net, layer)  # fmt: skip
        if missing:
            ctx.notes[self.id] = {"layers_without_copper_thickness": sorted(set(missing))}


def microstrip_z0(w: float, h: float, t: float, er: float) -> float:
    """IPC-2141 surface microstrip: Z0 = 87/√(εr+1.41) · ln(5.98h / (0.8w + t)). Valid for 0.1 < w/h < 2."""
    return 87 / math.sqrt(er + 1.41) * math.log(5.98 * h / (0.8 * w + t))


class ImpedanceCheck(Check):
    id = "impedance_estimate"
    version = "1.0.0"
    category = Category.SIGNAL_INTEGRITY
    title = "Impedance estimate (microstrip)"
    description = "Outer-layer track impedance vs the target you specify per net, from the board's stackup."

    def skip_reason(self, ctx: AnalysisContext) -> str | None:
        imp = ctx.options.get("impedance")
        if not isinstance(imp, dict) or not imp.get("nets"):
            return "No target impedances given (analysis option impedance.nets, ohms per net)."
        if ctx.design.stackup is None:
            return "The board file declares no stackup, so impedance can't be estimated."
        return None

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        imp: dict[str, Any] = ctx.options["impedance"]
        tol = float(imp.get("tolerance_pct", 10.0))
        stack = ctx.design.stackup.layers if ctx.design.stackup else []
        names = [s.name for s in stack]
        skipped: set[str] = set()
        for net, target in sorted(imp["nets"].items()):
            groups: dict[tuple[str, float], list[Track]] = defaultdict(list)
            for t in ctx.design.tracks:
                if t.net == net:
                    groups[(t.layer, round(t.width, 4))].append(t)
            for (layer, width), ts in sorted(groups.items()):
                if layer not in names or layer not in (ctx.copper_order[:1] + ctx.copper_order[-1:]):
                    skipped.add(layer)
                    continue
                i = names.index(layer)
                neighbour = stack[i + 1] if layer == ctx.copper_order[0] else stack[i - 1]
                cu = stack[i]
                if not (neighbour.thickness and neighbour.epsilon_r and cu.thickness) or neighbour.type == "copper":
                    skipped.add(layer)
                    continue
                h, er, tk = neighbour.thickness, neighbour.epsilon_r, cu.thickness
                if not 0.1 < width / h < 2.0:
                    skipped.add(f"{layer} (w/h outside the formula's range)")
                    continue
                z = microstrip_z0(width, h, tk, er)
                if abs(z - target) / target * 100 <= tol:
                    continue
                yield Finding(
                    check_id=self.id, rule="impedance_off_target", category=self.category, severity=Severity.MEDIUM,
                    title=f"{net}: ≈{z:.0f} Ω on {layer}, target {target:g} Ω",
                    description=f"{width:g} mm tracks on {layer} over {h * 1000:g} µm of εr {er:g} dielectric estimate to {z:.1f} Ω, outside {target:g} Ω ± {tol:g} %.",
                    explanation="Impedance mismatches cause reflections on fast signals. This is the IPC-2141 surface-microstrip approximation (typically within ±5-10 %), ignoring solder mask and nearby copper; confirm with your fabricator's impedance calculator.",
                    objects=[ObjectRef(kind=ObjectKind.NET, id=net, label=net), *_track_refs(ts)],
                    nets=[net], region=_region(ts), verification=Verification.HEURISTIC, confidence=0.7,
                    evidence=[Evidence(kind="measurement", label="Estimated impedance", value=f"{z:.1f} Ω", numeric_value=round(z, 2), unit="ohm", expected=f"{target:g} Ω ± {tol:g} %"),
                              Evidence(kind="reference", label="Formula", value="IPC-2141: Z0 = 87/√(εr+1.41) · ln(5.98h / (0.8w + t))"),
                              Evidence(kind="source_data", label="Stackup", value=f"w {width:g} mm, h {h:g} mm ({neighbour.name}), t {tk:g} mm, εr {er:g}")],
                    suggested_resolution="Adjust the track width (or stackup) to reach the target; confirm with the fabricator.",
                ).with_fingerprint(net, layer, f"{width:.4f}")  # fmt: skip
        if skipped:
            ctx.notes[self.id] = {
                "not_estimated": sorted(skipped),
                "note": "Inner layers (stripline) aren't estimated.",
            }


ROUTING_CHECKS = (DetourCheck, NetClassWidthCheck, CurrentCapacityCheck, ImpedanceCheck)
