"""Board outline presence and closure (exact)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from via_pcb.analysis.context import AnalysisContext
from via_pcb.analysis.findings import Category, Evidence, Finding, ObjectKind, ObjectRef, Region, Severity
from via_pcb.analysis.registry import Check
from via_pcb.models import Point

#: Endpoints closer than this are the same point (KiCad snaps to 1 nm internally; files use µm).
_TOLERANCE_DIGITS = 3


class BoardOutlineCheck(Check):
    id = "board_outline"
    version = "1.0.0"
    category = Category.BOARD_OUTLINE
    title = "Board outline"
    description = "The board needs one closed outline on Edge.Cuts: it defines the shape the fabricator cuts."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        outline = ctx.design.outline
        if not outline.graphics:
            bbox = ctx.design.bbox
            yield Finding(
                check_id=self.id,
                rule="outline_missing",
                category=self.category,
                severity=Severity.HIGH,
                title="No board outline",
                description="The design has no graphics on the Edge.Cuts layer.",
                explanation=(
                    "Fabricators cut the board along the Edge.Cuts outline. Without it the board size and "
                    "shape are undefined, and copper-to-edge clearance can't be checked."
                ),
                objects=[ObjectRef(kind=ObjectKind.OUTLINE, id="Edge.Cuts", label="Edge.Cuts")],
                region=Region(bbox=bbox) if bbox else None,
                evidence=[Evidence(kind="source_data", label="Edge.Cuts graphics", value="0", numeric_value=0)],
                suggested_resolution="Draw a closed board outline on Edge.Cuts.",
            ).with_fingerprint()
            return
        if outline.closed:
            return
        dangling = _dangling_endpoints(outline.graphics)
        evidence = [
            Evidence(
                kind="source_data", label="Edge.Cuts graphics", value=str(len(outline.graphics)),
                numeric_value=len(outline.graphics),
            ),
            Evidence(
                kind="measurement", label="Unjoined outline endpoints", value=str(len(dangling)),
                numeric_value=len(dangling), expected="0",
            ),
        ]  # fmt: skip
        evidence += [
            Evidence(kind="tool_output", label="Parser", value=w.message)
            for w in ctx.design.warnings
            if w.code == "open_outline"
        ]
        yield Finding(
            check_id=self.id,
            rule="outline_open",
            category=self.category,
            severity=Severity.HIGH,
            title="Board outline is not closed",
            description=(
                f"The Edge.Cuts outline has {len(dangling)} endpoint(s) that don't meet another outline "
                "segment, so it doesn't enclose an area."
            ),
            explanation=(
                "An open outline has no defined inside: fabrication tools may reject it or cut the wrong shape, "
                "and board area and edge clearances can't be computed."
            ),
            objects=[ObjectRef(kind=ObjectKind.OUTLINE, id="Edge.Cuts", label="Edge.Cuts")],
            region=Region(bbox=outline.bbox, points=dangling, layers=["Edge.Cuts"]) if outline.bbox else None,
            evidence=evidence,
            suggested_resolution="Join the marked endpoints so the outline forms closed loops.",
        ).with_fingerprint()


def _dangling_endpoints(graphics) -> list[Point]:
    """Endpoints of open outline pieces (lines, arcs) that no other piece shares."""
    counts: Counter[tuple[float, float]] = Counter()
    for g in graphics:
        if g.kind in {"line", "arc"} and len(g.points) >= 2:
            for p in (g.points[0], g.points[-1]):
                counts[(round(p.x, _TOLERANCE_DIGITS), round(p.y, _TOLERANCE_DIGITS))] += 1
    return [Point(x=x, y=y) for (x, y), n in sorted(counts.items()) if n % 2 == 1]


__all__ = ["BoardOutlineCheck"]
