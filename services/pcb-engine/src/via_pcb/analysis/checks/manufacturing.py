# ruff: noqa: E501  (user-facing finding texts read better unwrapped)
"""Manufacturability against a fabrication profile (exact geometry, VIA deterministic).

These checks answer "can a fabricator with these capabilities make this board?", which is a
different question from KiCad's DRC ("does the board follow its own design rules?"). Each finding
names the profile and the values used. Findings are grouped (by net, size or component) so a board
with a systematic issue yields a handful of findings, each listing its objects (up to 100) and markers.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

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
from via_pcb.analysis.shapes import (
    Owner,
    boxes_within,
    closest_points,
    core_distance,
    distance,
)
from via_pcb.models import BoundingBox, PadType, Point

MAX_OBJECTS = 100
MAX_POINTS = 50
#: Measurement tolerance (mm): covers arc chord error (<= 2 µm per side) so exact-limit designs aren't flagged.
EPS = 0.001


def _mm(v: float) -> str:
    return f"{v:.3f} mm".replace(".000 mm", " mm")


@dataclass
class _Group:
    objects: dict[str, ObjectRef] = field(default_factory=dict)
    points: list[Point] = field(default_factory=list)
    worst: float = float("inf")
    count: int = 0
    nets: set[str] = field(default_factory=set)
    components: set[str] = field(default_factory=set)
    layers: set[str] = field(default_factory=set)
    approx: bool = False

    def add(self, owner: Owner, value: float, point: tuple[float, float] | None, net: str | None = None,
            layer: str | None = None, approx: bool = False) -> None:  # fmt: skip
        self.count += 1
        self.worst = min(self.worst, value)
        if len(self.objects) < MAX_OBJECTS and owner.id:
            self.objects.setdefault(owner.id, _ref(owner))
        if point is not None and len(self.points) < MAX_POINTS:
            self.points.append(Point(x=point[0], y=point[1]))
        if net:
            self.nets.add(net)
        if owner.component:
            self.components.add(owner.component)
        if layer:
            self.layers.add(layer)
        self.approx = self.approx or approx

    def region(self) -> Region | None:
        if not self.points:
            return None
        xs, ys = [p.x for p in self.points], [p.y for p in self.points]
        return Region(
            bbox=BoundingBox(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys)),
            points=self.points,
            layers=sorted(self.layers),
        )


def _ref(owner: Owner) -> ObjectRef:
    return ObjectRef(kind=ObjectKind(owner.kind), id=owner.id, label=owner.label)


def _profile_evidence(ctx: AnalysisContext, label: str, required: float) -> list[Evidence]:
    p = ctx.profile
    return [
        Evidence(kind="rule", label=f"{label} ({p.name})", value=_mm(required), numeric_value=required, unit="mm"),
        Evidence(kind="reference", label="Profile source", value=p.source),
    ]


class _MfgCheck(Check):
    category = Category.MANUFACTURING

    def _finding(self, ctx: AnalysisContext, rule: str, key: str, group: _Group, *, title: str, description: str,
                 explanation: str, measured_label: str, required_label: str, required: float, severity: Severity,
                 resolution: str) -> Finding:  # fmt: skip
        return Finding(
            check_id=self.id,
            rule=rule,
            category=self.category,
            severity=severity,
            title=title,
            description=description,
            explanation=explanation,
            objects=list(group.objects.values()),
            components=sorted(group.components),
            nets=sorted(group.nets),
            region=group.region(),
            verification=Verification.HEURISTIC if group.approx else Verification.VERIFIED,
            confidence=0.7 if group.approx else 1.0,
            evidence=[
                Evidence(
                    kind="measurement",
                    label=measured_label,
                    value=_mm(group.worst),
                    numeric_value=round(group.worst, 4),
                    unit="mm",
                    expected=f">= {_mm(required)}",
                ),
                Evidence(kind="measurement", label="Occurrences", value=str(group.count), numeric_value=group.count),
                *_profile_evidence(ctx, required_label, required),
                *(
                    [
                        Evidence(
                            kind="reference",
                            label="Approximation",
                            value="Involves trapezoid, chamfered or custom pads, measured by their bounding rectangle.",
                        )
                    ]
                    if group.approx
                    else []
                ),
            ],
            suggested_resolution=resolution,
        ).with_fingerprint(rule, key)


class TrackWidthCheck(_MfgCheck):
    id = "mfg_track_width"
    version = "1.0.0"
    title = "Track width vs fabrication profile"
    description = "Tracks narrower than the profile's minimum track width."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        limit = ctx.profile.min_track_width
        groups: dict[str, _Group] = defaultdict(_Group)
        for t in ctx.design.tracks:
            if 0 < t.width < limit - EPS:
                owner = Owner("track", t.id or "", f"{'Arc track' if t.kind == 'arc' else 'Track'} on {t.layer}")
                mid = ((t.start.x + t.end.x) / 2, (t.start.y + t.end.y) / 2)
                groups[t.net or ""].add(owner, t.width, mid, t.net, t.layer)
        for net, g in sorted(groups.items()):
            name = net or "(no net)"
            yield self._finding(
                ctx, "track_too_narrow", net, g,
                title=f"Tracks on {name} are narrower than {_mm(limit)}",
                description=f"{g.count} track segment(s) on {name} are narrower than the profile minimum; the narrowest is {_mm(g.worst)}.",
                explanation="Tracks below a fabricator's minimum width may be over-etched or open, or need a more expensive process.",
                measured_label="Narrowest track", required_label="Minimum track width", required=limit,
                severity=Severity.MEDIUM, resolution="Widen these tracks or choose a fabricator/profile that supports them.",
            )  # fmt: skip


class ViaCheck(_MfgCheck):
    id = "mfg_vias"
    version = "1.0.0"
    title = "Vias vs fabrication profile"
    description = "Via drill, diameter and annular ring against the profile."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        p = ctx.profile
        rules = (
            ("via_drill_too_small", "Via drill", "Minimum drill", p.min_drill, lambda v: v.drill),
            ("via_too_small", "Via diameter", "Minimum via diameter", p.min_via_diameter, lambda v: v.diameter),
            ("via_annular_ring_too_small", "Via annular ring", "Minimum annular ring", p.min_annular_ring,
             lambda v: (v.diameter - v.drill) / 2),
        )  # fmt: skip
        for rule, what, req_label, limit, measure in rules:
            groups: dict[str, _Group] = defaultdict(_Group)
            for v in ctx.design.vias:
                value = measure(v)
                if value < limit - EPS:
                    owner = Owner("via", v.id or "", "Via" + (f" [{v.net}]" if v.net else ""))
                    groups[f"{v.diameter:.4f}/{v.drill:.4f}"].add(owner, value, (v.position.x, v.position.y), v.net)
            for size, g in sorted(groups.items()):
                dia, drill = size.split("/")
                yield self._finding(
                    ctx, rule, size, g,
                    title=f"{what} below {_mm(limit)} ({float(dia):g}/{float(drill):g} mm vias)",
                    description=f"{g.count} via(s) of {float(dia):g} mm diameter / {float(drill):g} mm drill have a {what.lower()} of {_mm(g.worst)}.",
                    explanation=_VIA_WHY[rule],
                    measured_label=what, required_label=req_label, required=limit,
                    severity=Severity.MEDIUM, resolution="Use a larger via size or a profile that supports this one.",
                )  # fmt: skip


_VIA_WHY = {
    "via_drill_too_small": "Holes below the fabricator's minimum drill need laser drilling or can't be made at all.",
    "via_too_small": "Via pads below the minimum diameter leave too little copper for drill registration tolerance.",
    "via_annular_ring_too_small": "A thin ring of copper around the hole can break out when the drill wanders.",
}


class PadHoleCheck(_MfgCheck):
    id = "mfg_pad_holes"
    version = "1.0.0"
    title = "Pad holes vs fabrication profile"
    description = "Through-hole pad drills and annular rings against the profile."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        p = ctx.profile
        drill_groups: dict[str, _Group] = defaultdict(_Group)
        ring_groups: dict[str, _Group] = defaultdict(_Group)
        for comp, pad in ctx.pads_with_component:
            if pad.drill is None or pad.drill.diameter <= 0:
                continue
            owner = Owner("pad", pad.id or "", f"{comp.reference} pad {pad.number}", comp.reference, pad.number)
            hole = min(pad.drill.diameter, pad.drill.slot_length or pad.drill.diameter)
            if hole < p.min_drill - EPS:
                drill_groups[comp.reference].add(owner, hole, (pad.position.x, pad.position.y), pad.net)
            if pad.type != PadType.THROUGH_HOLE:
                continue
            offset = abs(pad.drill.offset.x) + abs(pad.drill.offset.y) if pad.drill.offset else 0.0
            ring = (min(pad.size.x, pad.size.y) - hole) / 2 - offset
            approx = bool(pad.drill.slot_length or offset or pad.shape not in {"circle", "oval", "rect", "roundrect"})
            if ring < p.min_annular_ring - EPS:
                ring_groups[comp.reference].add(owner, ring, (pad.position.x, pad.position.y), pad.net, approx=approx)
        for ref, g in sorted(drill_groups.items()):
            yield self._finding(
                ctx, "pad_drill_too_small", ref, g,
                title=f"{ref}: pad holes below {_mm(p.min_drill)}",
                description=f"{g.count} pad hole(s) of {ref} are smaller than the profile minimum; the smallest is {_mm(g.worst)}.",
                explanation="Holes below the fabricator's minimum drill can't be drilled mechanically.",
                measured_label="Smallest hole", required_label="Minimum drill", required=p.min_drill,
                severity=Severity.MEDIUM, resolution="Use a footprint with larger holes or a profile that supports them.",
            )  # fmt: skip
        for ref, g in sorted(ring_groups.items()):
            yield self._finding(
                ctx, "pad_annular_ring_too_small", ref, g,
                title=f"{ref}: pad annular ring below {_mm(p.min_annular_ring)}",
                description=f"{g.count} through-hole pad(s) of {ref} leave {_mm(g.worst)} of copper around the hole at the narrowest point.",
                explanation="A thin copper ring around a plated hole can break when the drill wanders, opening the connection.",
                measured_label="Narrowest annular ring", required_label="Minimum annular ring", required=p.min_annular_ring,
                severity=Severity.MEDIUM, resolution="Enlarge the pads or reduce the hole size if the part's leads allow it.",
            )  # fmt: skip


class HoleSpacingCheck(_MfgCheck):
    id = "mfg_hole_spacing"
    version = "1.0.0"
    title = "Hole-to-hole spacing vs fabrication profile"
    description = "Pairs of holes whose edges are closer than the profile minimum."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        from via_pcb.analysis.shapes import Grid

        limit = ctx.profile.min_hole_to_hole
        holes = ctx.holes
        grid = Grid(cell=2.0)
        boxes = []
        for i, h in enumerate(holes):
            xs, ys = [p[0] for p in h.core], [p[1] for p in h.core]
            box = (min(xs) - h.radius, min(ys) - h.radius, max(xs) + h.radius, max(ys) + h.radius)
            boxes.append(box)
            grid.insert(i, box)
        groups: dict[str, _Group] = defaultdict(_Group)
        for i, a in enumerate(holes):
            for j in grid.query(boxes[i], limit):
                if j <= i or holes[j].owner.id == a.owner.id or not boxes_within(boxes[i], boxes[j], limit):
                    continue
                b = holes[j]
                gap = max(0.0, core_distance(a.core, b.core) - a.radius - b.radius)
                if gap < limit - EPS:
                    key = "|".join(sorted((a.owner.id, b.owner.id)))
                    g = groups[key]
                    g.add(a.owner, gap, closest_points(a.core, b.core))
                    g.add(b.owner, gap, None)
                    g.count -= 1
        for key, g in sorted(groups.items())[:200]:
            labels = " and ".join(o.label or o.id for o in g.objects.values())
            yield self._finding(
                ctx, "holes_too_close", key, g,
                title=f"Holes too close: {labels}",
                description=f"The holes of {labels} are {_mm(g.worst)} apart edge to edge.",
                explanation="Holes closer than the fabricator's minimum can break into each other or crack the board between them.",
                measured_label="Hole edge to hole edge", required_label="Minimum hole to hole", required=limit,
                severity=Severity.MEDIUM, resolution="Move the holes apart or use smaller drills.",
            )  # fmt: skip


class CopperToEdgeCheck(_MfgCheck):
    id = "mfg_copper_to_edge"
    version = "1.0.0"
    title = "Copper to board edge vs fabrication profile"
    description = "Pads, tracks and vias closer to the board outline than the profile minimum (zones excluded)."

    def skip_reason(self, ctx: AnalysisContext) -> str | None:
        return None if ctx.edge_segments else "The board has no outline."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        from via_pcb.analysis.shapes import Grid

        limit = ctx.profile.min_copper_to_edge
        edges = ctx.edge_segments
        grid = Grid(cell=2.0)
        for i, (a, b) in enumerate(edges):
            grid.insert(i, (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])))
        groups: dict[str, _Group] = defaultdict(_Group)
        for s in ctx.shapes:
            best, best_edge = float("inf"), None
            for k in grid.query(s.bbox, limit):
                a, b = edges[k]
                d = core_distance(s.core, (a, b)) - s.radius
                if d < best:
                    best, best_edge = d, (a, b)
            if best < limit - EPS and best_edge is not None:
                gap = max(0.0, best)
                groups[s.net or f"(no net) {s.owner.id}"].add(
                    s.owner, gap, closest_points(s.core, best_edge), s.net, s.layer, s.approx
                )
        for net, g in sorted(groups.items()):
            name = net if not net.startswith("(no net)") else "unconnected copper"
            yield self._finding(
                ctx, "copper_too_close_to_edge", net, g,
                title=f"Copper of {name} within {_mm(limit)} of the board edge",
                description=f"{len(g.objects)} item(s) of {name} come as close as {_mm(g.worst)} to the board outline.",
                explanation=(
                    "Copper near the edge can be exposed or damaged when the board is routed or scored out. "
                    "Edge connectors and castellated pads are intentional exceptions."
                ),
                measured_label="Closest copper to edge", required_label="Minimum copper to edge", required=limit,
                severity=Severity.MEDIUM, resolution="Pull the copper back from the edge, unless it is a deliberate edge feature.",
            )  # fmt: skip


class CopperSpacingCheck(_MfgCheck):
    id = "mfg_copper_spacing"
    version = "1.0.0"
    title = "Copper spacing vs fabrication profile"
    description = (
        "Copper of different nets closer than the profile's minimum clearance (pads, tracks and vias; "
        "zone fills aren't stored, so zones are left to KiCad DRC)."
    )

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        limit = ctx.profile.min_clearance
        shapes, grid = ctx.shapes, ctx.shape_grid
        groups: dict[str, _Group] = defaultdict(_Group)
        for i, a in enumerate(shapes):
            for j in grid.query(a.bbox, limit):
                if j <= i:
                    continue
                b = shapes[j]
                if b.layer != a.layer or b.owner.id == a.owner.id:
                    continue
                if a.net is not None and a.net == b.net:
                    continue
                if (
                    a.owner.component
                    and a.owner.component == b.owner.component
                    and a.owner.pad_number == b.owner.pad_number
                ):
                    continue  # same pad number in one footprint: connected inside the part
                if not boxes_within(a.bbox, b.bbox, limit):
                    continue
                gap = distance(a, b)
                if gap < limit - EPS:
                    nets = sorted((a.net or "(no net)", b.net or "(no net)"))
                    key = " / ".join(nets)
                    g = groups[key]
                    g.add(a.owner, gap, closest_points(a.core, b.core), a.net, a.layer, a.approx or b.approx)
                    g.add(b.owner, gap, None, b.net, b.layer, a.approx or b.approx)
                    g.count -= 1
        for key, g in sorted(groups.items()):
            yield self._finding(
                ctx, "copper_spacing_too_small", key, g,
                title=f"Copper spacing below {_mm(limit)}: {key}",
                description=f"Copper of {key} comes as close as {_mm(g.worst)} in {g.count} place(s) ({', '.join(sorted(g.layers))}).",
                explanation=(
                    "Gaps below the fabricator's minimum spacing can close up during etching, shorting the nets, "
                    "or force a more expensive process."
                ),
                measured_label="Smallest gap", required_label="Minimum clearance", required=limit,
                severity=Severity.HIGH, resolution="Increase the spacing, or confirm the fabricator can make it.",
            )  # fmt: skip


class SilkscreenWidthCheck(_MfgCheck):
    id = "mfg_silkscreen"
    version = "1.0.0"
    title = "Silkscreen line width vs fabrication profile"
    description = "Silkscreen lines thinner than the profile minimum (text isn't parsed, so it isn't checked)."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        limit = ctx.profile.min_silk_width
        groups: dict[str, _Group] = defaultdict(_Group)
        items = [("", None, g) for g in ctx.design.graphics] + [
            (c.reference, c, g) for c in ctx.design.components for g in c.graphics
        ]
        for _ref, comp, gr in items:
            if gr.layer not in ("F.SilkS", "B.SilkS") or gr.filled or not (0 < gr.width < limit - EPS):
                continue
            owner = (
                Owner("component", comp.id or comp.reference, comp.reference, comp.reference)
                if comp is not None
                else Owner("layer", gr.layer, gr.layer)
            )
            pt = gr.points[0]
            # Grouped by layer and width: library footprints share line widths, so this stays readable.
            groups[f"{gr.layer} {gr.width:.4f}"].add(owner, gr.width, (pt.x, pt.y), layer=gr.layer)
        for key, g in sorted(groups.items()):
            layer, width = key.split()
            who = f"{len(g.components)} component(s)" if g.components else "board graphics"
            if g.components and len(g.objects) < g.count:
                who += " and board graphics" if any(o.kind == "layer" for o in g.objects.values()) else ""
            yield self._finding(
                ctx, "silkscreen_too_thin", key, g,
                title=f"{_mm(float(width))} silkscreen lines on {layer}",
                description=f"{g.count} silkscreen line(s) on {layer} ({who}) are {_mm(float(width))} wide, below the profile minimum.",
                explanation="Silkscreen thinner than the printer's minimum may print broken or not at all.",
                measured_label="Thinnest line", required_label="Minimum silkscreen width", required=limit,
                severity=Severity.LOW, resolution="Thicken the lines (usually in the footprint library).",
            )  # fmt: skip


MANUFACTURING_CHECKS = (
    TrackWidthCheck, ViaCheck, PadHoleCheck, HoleSpacingCheck, CopperToEdgeCheck, CopperSpacingCheck,
    SilkscreenWidthCheck,
)  # fmt: skip
