"""Connectivity starter check: copper pads with no net (the fact is exact; its meaning needs judgement)."""

from __future__ import annotations

import math
from collections.abc import Iterable

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
from via_pcb.analysis.shapes import Owner, boxes_within, distance, point_in_polygon, segment_segment_distance
from via_pcb.models import BoundingBox, Component, Pad, PadType, Point


class PadsWithoutNetCheck(Check):
    id = "pads_without_net"
    version = "1.0.0"
    category = Category.CONNECTIVITY
    title = "Copper pads without a net"
    description = "Copper pads that aren't assigned to any net, grouped by component."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        copper = ctx.copper_layers
        for comp in ctx.design.components:
            pads = [p for p in comp.pads if not p.net and p.type != PadType.NPTH and copper.intersection(p.layers)]
            if not pads:
                continue
            numbers = ", ".join(p.number or "?" for p in pads)
            xs = [p.position.x for p in pads]
            ys = [p.position.y for p in pads]
            yield Finding(
                check_id=self.id,
                rule="copper_pad_no_net",
                category=self.category,
                severity=Severity.LOW,
                title=f"{comp.reference or comp.footprint}: copper pad(s) without a net",
                description=f"{len(pads)} copper pad(s) of {comp.reference} ({comp.footprint}) have no net: {numbers}.",
                explanation=(
                    "A copper pad with no net isn't connected to anything electrically. That's often intended "
                    "(mounting holes, mechanical or unused pins), but it can also mean a missing connection or "
                    "a schematic/board mismatch. Confirm against the schematic."
                ),
                objects=[ObjectRef(kind=ObjectKind.COMPONENT, id=comp.id or comp.reference, label=comp.reference)]
                + [
                    ObjectRef(
                        kind=ObjectKind.PAD,
                        id=p.id or f"{comp.reference}/{p.number}",
                        label=f"{comp.reference} pad {p.number}",
                    )
                    for p in pads
                ],
                components=[comp.reference] if comp.reference else [],
                region=Region(
                    bbox=BoundingBox(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys)),
                    points=[p.position for p in pads],
                    layers=sorted({layer for p in pads for layer in p.layers if layer in copper}),
                ),
                evidence=[
                    Evidence(kind="source_data", label="Pads without net", value=numbers, numeric_value=len(pads)),
                    Evidence(kind="source_data", label="Footprint", value=comp.footprint),
                ],
                suggested_resolution="If these pads should connect, assign them in the schematic and update the board.",
            ).with_fingerprint(comp.id or comp.reference, *sorted(p.number for p in pads))


# --- Copper connectivity graph -----------------------------------------------------------------

#: Items closer than this (mm) count as touching.
TOUCH = 0.001


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _owner_key(owner: Owner) -> str:
    # Pads with the same number in one footprint are connected inside the part (e.g. split thermal pads).
    if owner.kind == "pad" and owner.component and owner.pad_number:
        return f"pad:{owner.component}/{owner.pad_number}"
    return f"{owner.kind}:{owner.id}"


def connectivity(ctx: AnalysisContext) -> tuple[_UnionFind, set[str]]:
    """Union-find over copper owners joined by same-net copper contact (and same-net zone outlines).

    Returns the structure and the nets whose connectivity relied on a zone outline (zone fills
    aren't stored, so the outline stands in for the fill: an approximation).
    """
    uf = _UnionFind()
    shapes = ctx.shapes
    grid = ctx.shape_grid
    for i, a in enumerate(shapes):
        if a.net is None:
            continue
        ka = _owner_key(a.owner)
        uf.find(ka)
        for j in grid.query(a.bbox, TOUCH):
            if j <= i:
                continue
            b = shapes[j]
            if b.net != a.net or b.layer != a.layer or not boxes_within(a.bbox, b.bbox, TOUCH):
                continue
            kb = _owner_key(b.owner)
            if ka != kb and uf.find(ka) != uf.find(kb) and distance(a, b) <= TOUCH:
                uf.union(ka, kb)
    zone_nets: set[str] = set()
    for zone in ctx.design.zones:
        if zone.keepout or not zone.net or len(zone.outline) < 3:
            continue
        poly = [(p.x, p.y) for p in zone.outline]
        zkey = f"zone:{zone.id or id(zone)}"
        layers = set(zone.layers)
        for s in shapes:
            if s.net != zone.net or s.layer not in layers:
                continue
            inside = any(point_in_polygon(p, poly) for p in s.core)
            near = (
                inside
                or min(
                    segment_segment_distance(p, q, poly[k], poly[(k + 1) % len(poly)])
                    for p, q in (
                        zip(s.core, s.core[1:] + s.core[:1], strict=False)
                        if len(s.core) > 1
                        else [(s.core[0], s.core[0])]
                    )
                    for k in range(len(poly))
                )
                <= s.radius
            )
            if near:
                uf.union(zkey, _owner_key(s.owner))
                zone_nets.add(zone.net)
    return uf, zone_nets


class CopperIslandsCheck(Check):
    id = "copper_islands"
    version = "1.0.0"
    category = Category.CONNECTIVITY
    title = "Unrouted connections"
    description = (
        "Pads of the same net that copper doesn't join (VIA's own connectivity graph). "
        "Skipped when KiCad DRC ran, whose unconnected-items check is authoritative."
    )

    def skip_reason(self, ctx: AnalysisContext) -> str | None:
        drc = ctx.options.get("kicad_drc")
        if isinstance(drc, dict) and isinstance(drc.get("report"), dict):
            return "KiCad DRC ran; its unconnected-items results are used instead."
        return None

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        uf, zone_nets = connectivity(ctx)
        pads_by_net: dict[str, dict[str, list[tuple[Component, Pad]]]] = {}
        for comp, pad in ctx.pads_with_component:
            if not pad.net or pad.type == PadType.NPTH or not ctx.copper_layers.intersection(pad.layers):
                continue
            owner_key = f"pad:{comp.reference}/{pad.number}" if comp.reference and pad.number else f"pad:{pad.id}"
            pads_by_net.setdefault(pad.net, {}).setdefault(uf.find(owner_key), []).append((comp, pad))
        approx_pads = {s.owner.id for s in ctx.shapes if s.approx and s.owner.kind == "pad"}
        for net, islands in sorted(pads_by_net.items()):
            if len(islands) < 2:
                continue
            groups = sorted(islands.values(), key=len, reverse=True)
            gaps = _ratsnest(groups)
            uses_zone = net in zone_nets
            approx = uses_zone or any(p.id in approx_pads for g in groups for _, p in g)
            all_pads = [cp for g in groups for cp in g]
            yield Finding(
                check_id=self.id,
                rule="net_not_connected",
                category=self.category,
                severity=Severity.MEDIUM if approx else Severity.HIGH,
                title=f"Net {net} isn't fully connected",
                description=(
                    f"Net {net}'s {len(all_pads)} pads form {len(groups)} separate copper groups; "
                    f"{len(groups) - 1} connection(s) are missing."
                ),
                explanation=(
                    "Pads on the same net must be joined by copper. Unjoined groups mean the board doesn't "
                    "implement the schematic connection until they're routed."
                    + (
                        " This net uses a zone; VIA approximates the zone's fill by its outline, so check in KiCad."
                        if uses_zone
                        else ""
                    )
                ),
                objects=[
                    ObjectRef(kind=ObjectKind.NET, id=net, label=net),
                    *[
                        ObjectRef(kind=ObjectKind.PAD, id=p.id or "", label=f"{c.reference} pad {p.number}")
                        for c, p in all_pads[:100]
                    ],
                ],
                components=sorted({c.reference for c, _ in all_pads if c.reference}),
                nets=[net],
                region=Region(
                    bbox=BoundingBox(
                        min_x=min(p.position.x for _, p in all_pads),
                        min_y=min(p.position.y for _, p in all_pads),
                        max_x=max(p.position.x for _, p in all_pads),
                        max_y=max(p.position.y for _, p in all_pads),
                    ),
                    points=[pt for gap in gaps for pt in gap[1:]],
                ),
                verification=Verification.HEURISTIC if approx else Verification.VERIFIED,
                confidence=0.6 if approx else 0.95,
                evidence=[
                    Evidence(
                        kind="measurement",
                        label="Copper groups",
                        value=str(len(groups)),
                        numeric_value=len(groups),
                        expected="1",
                    ),
                    Evidence(kind="measurement", label="Pads per group", value=", ".join(str(len(g)) for g in groups)),
                    *[
                        Evidence(
                            kind="measurement",
                            label="Shortest missing connection",
                            value=f"{d:.2f} mm",
                            numeric_value=round(d, 4),
                            unit="mm",
                        )
                        for d, _, _ in gaps[:1]
                    ],
                ],
                suggested_resolution="Route the missing connections (the markers show the nearest pad pairs).",
            ).with_fingerprint(net)


def _ratsnest(groups: list[list[tuple[Component, Pad]]]) -> list[tuple[float, Point, Point]]:
    """Nearest pad pairs joining the groups (Prim's algorithm over groups), shortest first."""
    joined = [groups[0]]
    rest = groups[1:]
    out: list[tuple[float, Point, Point]] = []
    while rest:
        best: tuple[float, int, Point, Point] | None = None
        for gi, g in enumerate(rest):
            for _, a in g:
                for j in joined:
                    for _, b in j:
                        d = math.hypot(a.position.x - b.position.x, a.position.y - b.position.y)
                        if best is None or d < best[0]:
                            best = (d, gi, a.position, b.position)
        assert best is not None
        out.append((best[0], best[2], best[3]))
        joined.append(rest.pop(best[1]))
    return sorted(out, key=lambda x: x[0])


class SinglePadNetsCheck(Check):
    id = "single_pad_nets"
    version = "1.0.0"
    category = Category.CONNECTIVITY
    title = "Nets with a single pad"
    description = (
        "Nets that reach only one pad. KiCad's names for pins connected to nothing ('unconnected-…', and "
        "KiCad 5's 'Net-(REF-PadN)' on that same pad) are excluded."
    )

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        counts: dict[str, list[tuple[Component, Pad]]] = {}
        for comp, pad in ctx.pads_with_component:
            if pad.net:
                counts.setdefault(pad.net, []).append((comp, pad))
        kicad5 = (ctx.kicad_file_version or 0) and (ctx.kicad_file_version or 0) <= 20171130
        for net, pads in sorted(counts.items()):
            if len(pads) != 1 or net.startswith("unconnected-"):
                continue
            comp, pad = pads[0]
            if kicad5 and net in {
                f"Net-({comp.reference}-Pad{pad.number})",
                f"/Net-({comp.reference}-Pad{pad.number})",
            }:
                continue  # KiCad 5's auto name for a pin connected to nothing (KiCad 6+: "unconnected-(...)")
            yield Finding(
                check_id=self.id,
                rule="single_pad_net",
                category=self.category,
                severity=Severity.LOW,
                title=f"Net {net} reaches only one pad",
                description=f"Net {net} connects only {comp.reference} pad {pad.number}.",
                explanation=(
                    "A net with one pad connects nothing. It's often a test point or a deliberately unused "
                    "signal, but it can also be a missing connection in the schematic."
                ),
                objects=[
                    ObjectRef(kind=ObjectKind.NET, id=net, label=net),
                    ObjectRef(kind=ObjectKind.PAD, id=pad.id or "", label=f"{comp.reference} pad {pad.number}"),
                ],
                components=[comp.reference] if comp.reference else [],
                nets=[net],
                region=Region(
                    bbox=BoundingBox(
                        min_x=pad.position.x, min_y=pad.position.y, max_x=pad.position.x, max_y=pad.position.y
                    ),
                    points=[pad.position],
                ),
                evidence=[Evidence(kind="source_data", label="Pads on net", value="1", numeric_value=1)],
                suggested_resolution="Check the schematic; connect it or mark the pin as not connected.",
            ).with_fingerprint(net)


class CopperLayerUsageCheck(Check):
    id = "copper_layer_usage"
    version = "1.0.0"
    category = Category.ROUTING
    title = "Copper layer usage"
    description = "Copper layers with no tracks, zones or SMD pads (only through-hole pads and vias pass through)."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        stats: dict[str, dict[str, float]] = {
            name: {"tracks": 0, "track_length_mm": 0.0, "zones": 0, "smd_pads": 0} for name in ctx.copper_order
        }
        for t in ctx.design.tracks:
            if t.layer in stats:
                stats[t.layer]["tracks"] += 1
                stats[t.layer]["track_length_mm"] += t.length
        for z in ctx.design.zones:
            if not z.keepout:
                for layer in z.layers:
                    if layer in stats:
                        stats[layer]["zones"] += 1
        for _, p in ctx.pads_with_component:
            if p.type in (PadType.SMD, PadType.CONNECT):
                for layer in p.layers:
                    if layer in stats:
                        stats[layer]["smd_pads"] += 1
        ctx.notes[self.id] = {k: {**v, "track_length_mm": round(v["track_length_mm"], 1)} for k, v in stats.items()}
        for name, s in stats.items():
            if s["tracks"] == 0 and s["zones"] == 0 and s["smd_pads"] == 0:
                yield Finding(
                    check_id=self.id,
                    rule="copper_layer_unused",
                    category=self.category,
                    severity=Severity.INFO,
                    title=f"{name} carries no routing",
                    description=(
                        f"Copper layer {name} has no tracks, zones or SMD pads; only through-hole pads and vias "
                        "pass through it."
                    ),
                    explanation=(
                        "An unused copper layer adds cost without adding routing. It may be intentional "
                        "(stackup symmetry, a future plane), or a chance to reduce the layer count."
                    ),
                    objects=[ObjectRef(kind=ObjectKind.LAYER, id=name, label=name)],
                    evidence=[
                        Evidence(kind="measurement", label="Tracks", value="0", numeric_value=0),
                        Evidence(kind="measurement", label="Zones", value="0", numeric_value=0),
                        Evidence(kind="measurement", label="SMD pads", value="0", numeric_value=0),
                    ],
                ).with_fingerprint(name)
