"""Connectivity starter check: copper pads with no net (the fact is exact; its meaning needs judgement)."""

from __future__ import annotations

from collections.abc import Iterable

from via_pcb.analysis.context import AnalysisContext
from via_pcb.analysis.findings import Category, Evidence, Finding, ObjectKind, ObjectRef, Region, Severity
from via_pcb.analysis.registry import Check
from via_pcb.models import BoundingBox, PadType


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
