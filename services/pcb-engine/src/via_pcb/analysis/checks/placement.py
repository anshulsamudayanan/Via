# ruff: noqa: E501  (user-facing finding texts read better unwrapped)
"""Placement and board-space checks (VIA deterministic; measurements exact, meaning heuristic).

These look at how parts are arranged. The numbers are measured exactly from the design; whether
they're a problem depends on intent, so most findings are ``heuristic`` with confidence below 1
and say what would make them intended.
"""

from __future__ import annotations

import math
import re
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
from via_pcb.analysis.shapes import core_distance
from via_pcb.models import BoundingBox, Component, Point

#: Power and ground net names (hierarchical "/" prefixes are ignored). Heuristic by nature.
POWER_RE = re.compile(
    r"^(\+?\d+(\.\d+)?V\d*|\+?\d+V\d+|V(CC|DD|BAT|IN|BUS|SYS|REF)\w*|AVCC|DVCC|AVDD|DVDD|VDDA|VDDIO|\+\w+)$", re.I
)
GROUND_RE = re.compile(r"^(GND\w*|\w*GND|VSS\w*|AGND|DGND|PGND|0V)$", re.I)
CONNECTOR_REF = re.compile(r"^(J|P|CN|CON|X|USB)\d", re.I)
IC_REF = re.compile(r"^(U|IC)\d", re.I)
CAP_REF = re.compile(r"^C\d", re.I)


def _base(net: str) -> str:
    return net.rsplit("/", 1)[-1]


def is_power(net: str | None) -> bool:
    return bool(net) and not is_ground(net) and bool(POWER_RE.match(_base(net or "")))


def is_ground(net: str | None) -> bool:
    return bool(net) and bool(GROUND_RE.match(_base(net or "")))


def extent(c: Component) -> BoundingBox | None:
    """A component's footprint extent: courtyard if it has one, else pads and fab/silk graphics."""
    pts = [(p.x, p.y) for g in c.graphics if "CrtYd" in g.layer for p in g.points]
    if not pts:
        for p in c.pads:
            hw, hh = max(p.size.x, p.size.y) / 2, max(p.size.x, p.size.y) / 2
            pts += [(p.position.x - hw, p.position.y - hh), (p.position.x + hw, p.position.y + hh)]
    if not pts:
        pts = [(c.position.x, c.position.y)]
    return BoundingBox(min_x=min(x for x, _ in pts), min_y=min(y for _, y in pts),
                       max_x=max(x for x, _ in pts), max_y=max(y for _, y in pts))  # fmt: skip


class OrientationCheck(Check):
    id = "placement_orientation"
    version = "1.0.0"
    category = Category.PLACEMENT
    title = "Non-orthogonal component rotation"
    description = "Components rotated by angles that aren't multiples of 90°."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        odd = [
            c
            for c in ctx.design.components
            if abs((c.rotation + 1e-9) % 90) > 0.01 and abs(c.rotation % 90 - 90) > 0.01
        ]
        if not odd:
            return
        yield Finding(
            check_id=self.id, rule="non_orthogonal_rotation", category=self.category, severity=Severity.INFO,
            title=f"{len(odd)} component(s) at non-orthogonal angles",
            description="Rotated by angles that aren't multiples of 90°: " + ", ".join(f"{c.reference} ({c.rotation:g}°)" for c in odd[:30]) + (" ..." if len(odd) > 30 else "") + ".",
            explanation="Assembly machines handle any angle, but odd angles are often accidental and make routing, inspection and panelisation harder. Intentional for radial layouts.",
            objects=[ObjectRef(kind=ObjectKind.COMPONENT, id=c.id or c.reference, label=c.reference) for c in odd[:100]],
            components=sorted(c.reference for c in odd if c.reference),
            region=Region(bbox=BoundingBox(min_x=min(c.position.x for c in odd), min_y=min(c.position.y for c in odd),
                                           max_x=max(c.position.x for c in odd), max_y=max(c.position.y for c in odd)),
                          points=[c.position for c in odd[:50]]),
            evidence=[Evidence(kind="source_data", label="Rotations", value=", ".join(sorted({f"{c.rotation:g}°" for c in odd})))],
        ).with_fingerprint(*sorted(c.id or c.reference for c in odd))  # fmt: skip


class ConnectorEdgeCheck(Check):
    id = "connector_edge_access"
    version = "1.0.0"
    category = Category.PLACEMENT
    title = "Connectors away from the board edge"
    description = (
        "Connectors (J/P/CN/X/USB references or connector footprints) whose footprint doesn't come near any board edge."
    )

    def skip_reason(self, ctx: AnalysisContext) -> str | None:
        return None if ctx.edge_segments else "The board has no outline."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        bbox = ctx.design.outline.bbox
        assert bbox is not None
        limit = max(5.0, 0.1 * min(bbox.width, bbox.height))
        for c in ctx.design.components:
            if not (CONNECTOR_REF.match(c.reference or "") or "connector" in c.footprint.lower()):
                continue
            e = extent(c)
            if e is None:
                continue
            box = ((e.min_x, e.min_y), (e.max_x, e.min_y), (e.max_x, e.max_y), (e.min_x, e.max_y))
            gap = min(core_distance(box, seg) for seg in ctx.edge_segments)
            if gap <= limit:
                continue
            yield Finding(
                check_id=self.id, rule="connector_not_at_edge", category=self.category, severity=Severity.LOW,
                title=f"{c.reference} is {gap:.1f} mm from the board edge",
                description=f"Connector {c.reference} ({c.footprint}) sits {gap:.1f} mm inside the board; the nearest edge is farther than {limit:.1f} mm.",
                explanation="Cable and mating connectors are usually placed at an edge so the plug can reach them and cables don't cross the board. Internal headers (programming, jumpers, board-to-board) are fine where they are.",
                objects=[ObjectRef(kind=ObjectKind.COMPONENT, id=c.id or c.reference, label=c.reference)],
                components=[c.reference], region=Region(bbox=e, points=[c.position]),
                verification=Verification.HEURISTIC, confidence=0.5,
                evidence=[Evidence(kind="measurement", label="Footprint to nearest edge", value=f"{gap:.2f} mm", numeric_value=round(gap, 3), unit="mm", expected=f"<= {limit:.1f} mm")],
                suggested_resolution="If a cable plugs in here, consider moving it to the edge.",
            ).with_fingerprint(c.id or c.reference)  # fmt: skip


class DecouplingCheck(Check):
    id = "decoupling_proximity"
    version = "1.0.0"
    category = Category.POWER
    title = "Decoupling capacitor proximity"
    description = "IC power pins (by net name) without a capacitor from that net to ground nearby."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        limit = float(ctx.options.get("decoupling_max_distance_mm", 5.0))
        caps: dict[str, list[tuple[Component, Point]]] = {}
        for c in ctx.design.components:
            if CAP_REF.match(c.reference or "") and len(c.pads) == 2:
                nets = [p.net for p in c.pads]
                if any(is_ground(n) for n in nets):
                    for p in c.pads:
                        if is_power(p.net):
                            caps.setdefault(p.net or "", []).append((c, p.position))
        for ic in ctx.design.components:
            if not IC_REF.match(ic.reference or "") or len(ic.pads) < 4:
                continue
            problems: list[tuple[str, str, float | None, str | None, Point]] = []
            for pad in ic.pads:
                if not is_power(pad.net):
                    continue
                candidates = caps.get(pad.net or "", [])
                if not candidates:
                    problems.append((pad.number, pad.net or "", None, None, pad.position))
                    continue
                cap, pos = min(
                    candidates, key=lambda cp: math.dist((cp[1].x, cp[1].y), (pad.position.x, pad.position.y))
                )
                d = math.dist((pos.x, pos.y), (pad.position.x, pad.position.y))
                if d > limit:
                    problems.append((pad.number, pad.net or "", d, cap.reference, pad.position))
            if not problems:
                continue
            lines = [
                f"pin {n} ({net}): "
                + (f"nearest {cap} at {d:.1f} mm" if d is not None else "no capacitor to ground on this net")
                for n, net, d, cap, _ in problems
            ]
            yield Finding(
                check_id=self.id, rule="decoupling_far_or_missing", category=self.category, severity=Severity.LOW,
                title=f"{ic.reference}: power pins without a nearby decoupling capacitor",
                description=f"{ic.reference}: " + "; ".join(lines[:12]) + ("; ..." if len(lines) > 12 else "") + ".",
                explanation=f"Decoupling capacitors supply fast current to an IC's power pins; the farther away, the more inductance in the loop and the less they help. VIA identifies power and ground by net name and capacitors by reference, and uses {limit:g} mm from pad to pad as its threshold, so this is a heuristic: check the datasheet's recommendations.",
                objects=[ObjectRef(kind=ObjectKind.COMPONENT, id=ic.id or ic.reference, label=ic.reference)],
                components=[ic.reference], nets=sorted({net for _, net, _, _, _ in problems}),
                region=Region(bbox=BoundingBox(min_x=min(p.x for *_, p in problems), min_y=min(p.y for *_, p in problems),
                                               max_x=max(p.x for *_, p in problems), max_y=max(p.y for *_, p in problems)),
                              points=[p for *_, p in problems]),
                verification=Verification.HEURISTIC, confidence=0.6,
                evidence=[Evidence(kind="measurement", label=f"Pin {n} ({net})", value=f"{d:.2f} mm to {cap}" if d is not None else "no capacitor found",
                                   numeric_value=round(d, 3) if d is not None else None, unit="mm" if d is not None else None, expected=f"<= {limit:g} mm")
                          for n, net, d, cap, _ in problems[:20]],
                suggested_resolution="Place a decoupling capacitor next to each power pin, with short connections to power and ground.",
            ).with_fingerprint(ic.id or ic.reference, *sorted(n for n, *_ in problems))  # fmt: skip


class BoardSpaceCheck(Check):
    id = "board_space"
    version = "1.0.0"
    category = Category.GEOMETRY
    title = "Unused board space"
    description = "Margins between the outline and the area occupied by components."

    def skip_reason(self, ctx: AnalysisContext) -> str | None:
        if not ctx.design.outline.closed or ctx.design.outline.bbox is None:
            return "The board has no closed outline."
        return None if ctx.design.components else "The board has no components."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        board = ctx.design.outline.bbox
        assert board is not None
        boxes = [b for c in ctx.design.components if (b := extent(c)) is not None]
        used = BoundingBox(min_x=min(b.min_x for b in boxes), min_y=min(b.min_y for b in boxes),
                           max_x=max(b.max_x for b in boxes), max_y=max(b.max_y for b in boxes))  # fmt: skip
        margins = {"left": used.min_x - board.min_x, "right": board.max_x - used.max_x,
                   "top": used.min_y - board.min_y, "bottom": board.max_y - used.max_y}  # fmt: skip
        ctx.notes[self.id] = {"board_mm": [round(board.width, 2), round(board.height, 2)],
                              "components_extent_mm": [round(used.width, 2), round(used.height, 2)],
                              "margins_mm": {k: round(v, 2) for k, v in margins.items()}}  # fmt: skip
        large = {side: m for side, m in margins.items()
                 if m > max(5.0, 0.15 * (board.width if side in ("left", "right") else board.height))}  # fmt: skip
        if not large:
            return
        keep = 2.0  # mm left around components if the outline were tightened (illustrative, stated)
        w = board.width - sum(max(0.0, large.get(s, 0) - keep) for s in ("left", "right"))
        h = board.height - sum(max(0.0, large.get(s, 0) - keep) for s in ("top", "bottom"))
        yield Finding(
            check_id=self.id, rule="unused_margin", category=self.category, severity=Severity.INFO,
            title="Board has large empty margins",
            description="Empty space between the components and the outline: " + ", ".join(f"{s} {m:.1f} mm" for s, m in large.items()) + ".",
            explanation=f"Unused area costs money in every board. Tightening the outline to {keep:g} mm around the components on those sides would give about {w:.1f} x {h:.1f} mm instead of {board.width:.1f} x {board.height:.1f} mm. Margins may be intended (enclosure fit, mounting, handling).",
            objects=[ObjectRef(kind=ObjectKind.OUTLINE, id="Edge.Cuts", label="Board outline")],
            region=Region(bbox=board), verification=Verification.HEURISTIC, confidence=0.7,
            evidence=[*(Evidence(kind="measurement", label=f"{s.capitalize()} margin", value=f"{m:.2f} mm", numeric_value=round(m, 3), unit="mm") for s, m in margins.items()),
                      Evidence(kind="measurement", label="Board", value=f"{board.width:.2f} x {board.height:.2f} mm"),
                      Evidence(kind="measurement", label="Components extent", value=f"{used.width:.2f} x {used.height:.2f} mm")],
            suggested_resolution="If the enclosure allows, shrink the outline (VIA Optimize can propose this as a candidate).",
        ).with_fingerprint("margins")  # fmt: skip


PLACEMENT_CHECKS = (OrientationCheck, ConnectorEdgeCheck, DecouplingCheck, BoardSpaceCheck)
