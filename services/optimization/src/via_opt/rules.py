# ruff: noqa: E501
"""Constraint evaluation: every constraint is evaluated on (original, modified) and reports its own status.

``not_applicable`` means the change can't affect the constraint. ``unverified`` means VIA has no way to
check it (a requirement the engineer declared, or routed connectivity after moving routed parts): it is
never counted as satisfied. Hard constraints must all be satisfied for a candidate to be validated.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from via_opt.changes import Change, ChangeKind
from via_opt.constraints import Constraints, is_fixed, keepout_polygons, overlaps
from via_pcb.analysis.checks.placement import extent
from via_pcb.analysis.shapes import point_in_polygon
from via_pcb.models import BoundingBox, Component, PCBDesign

TOL = 1e-3  # mm: coordinates are stored rounded to 3 decimals


class ConstraintStatus(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNVERIFIED = "unverified"
    NOT_APPLICABLE = "not_applicable"


class ConstraintResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["hard", "soft"] = "hard"
    status: ConstraintStatus
    detail: str = ""
    violations: list[str] = Field(default_factory=list)


def _result(cid: str, applicable: bool, found: list[str], ok: str) -> ConstraintResult:
    if not applicable:
        return ConstraintResult(id=cid, status=ConstraintStatus.NOT_APPLICABLE)
    if found:
        return ConstraintResult(id=cid, status=ConstraintStatus.VIOLATED, detail=found[0], violations=found[:20])
    return ConstraintResult(id=cid, status=ConstraintStatus.SATISFIED, detail=ok)


def _margin(e: BoundingBox, ob: BoundingBox) -> float:
    return min(e.min_x - ob.min_x, e.min_y - ob.min_y, ob.max_x - e.max_x, ob.max_y - e.max_y)


def routed_moves(design: PCBDesign, changes: list[Change]) -> list[str]:
    """References of moved/rotated components whose pads have tracks on their nets."""
    routed_nets = {t.net for t in design.tracks if t.net}
    comps = {c.id: c for c in design.components}
    out = []
    for ch in changes:
        if ch.kind in (ChangeKind.MOVE_COMPONENT, ChangeKind.ROTATE_COMPONENT):
            c = comps.get(ch.target.id)
            if c is not None and any(p.net in routed_nets for p in c.pads):
                out.append(c.reference)
    return out


def _pad_nets(design: PCBDesign) -> dict[tuple[str, int], str | None]:
    return {(c.id or c.reference, i): p.net for c in design.components for i, p in enumerate(c.pads)}


def evaluate(before: PCBDesign, after: PCBDesign, changes: list[Change], cons: Constraints) -> list[ConstraintResult]:
    old = {c.id: c for c in before.components if c.id}
    moved: list[tuple[Component, Component]] = []  # (before, after)
    for c in after.components:
        o = old.get(c.id or "")
        if o is not None and (
            abs(o.position.x - c.position.x) > 1e-6
            or abs(o.position.y - c.position.y) > 1e-6
            or abs(o.rotation - c.rotation) > 1e-6
        ):
            moved.append((o, c))
    ob = after.outline.bbox
    outline_changed = before.outline.bbox != after.outline.bbox
    # Parts to check against the outline: the moved ones, or all of them when the outline itself changed.
    scope = [(old.get(c.id or "", c), c) for c in after.components] if outline_changed else moved
    out: list[ConstraintResult] = []

    # Identity and netlist: the invariants every candidate must keep.
    ids_before = sorted((c.id or "", c.reference) for c in before.components)
    ids_after = sorted((c.id or "", c.reference) for c in after.components)
    out.append(_result("component_identity", True, [] if ids_before == ids_after else ["Components were added, removed or renamed"],
                       "The same components, with the same references."))  # fmt: skip
    nets_changed = (
        _pad_nets(before) != _pad_nets(after)
        or [(t.id, t.net) for t in before.tracks] != [(t.id, t.net) for t in after.tracks]
        or [(v.id, v.net) for v in before.vias] != [(v.id, v.net) for v in after.vias]
    )
    out.append(_result("net_connectivity", True, ["A pad, track or via changed net"] if nets_changed else [],
                       "Every pad, track and via keeps its net (the netlist is unchanged). Routed continuity is reported separately."))  # fmt: skip

    out.append(_result("fixed_components", bool(moved), [f"{a.reference} is fixed but would move" for b, a in moved if is_fixed(b, cons)],
                       "No fixed, locked, connector or mounting part moves."))  # fmt: skip

    inside: list[str] = []
    margin: list[str] = []
    if ob is not None:
        for b, a in scope:
            e, eb = extent(a), extent(b)
            if e is None:
                continue
            m_after = _margin(e, ob)
            m_before = _margin(eb, before.outline.bbox) if eb is not None and before.outline.bbox is not None else None
            if m_after < -1e-6 and not (m_before is not None and m_before < -1e-6 and m_after >= m_before - TOL):
                inside.append(f"{a.reference} would extend past the board outline")
            elif m_before is not None and m_after < min(cons.edge_margin_mm, m_before) - TOL:
                margin.append(
                    f"{a.reference} would be {max(m_after, 0):.2f} mm from the edge (needs {cons.edge_margin_mm:g} mm)"
                )
    out.append(
        _result(
            "within_outline", ob is not None and bool(scope), inside, "Every affected part stays inside the outline."
        )
    )
    out.append(
        _result(
            "edge_margin",
            ob is not None and bool(scope),
            margin,
            f"Affected parts keep {cons.edge_margin_mm:g} mm from the edge.",
        )
    )

    clash: list[str] = []
    if moved:
        boxes_after = {c.id: e for c in after.components if c.id and (e := extent(c)) is not None}
        boxes_before = {c.id: e for c in before.components if c.id and (e := extent(c)) is not None}
        for _, a in moved:
            ea = boxes_after.get(a.id or "")
            if ea is None:
                continue
            for oid, other in boxes_after.items():
                if oid == a.id or not overlaps(ea, other, cons.component_gap_mm):
                    continue
                eb, ob_other = boxes_before.get(a.id or ""), boxes_before.get(oid)
                if eb is not None and ob_other is not None and overlaps(eb, ob_other, cons.component_gap_mm):
                    continue  # already this close before the change: not made worse
                names = {c.id: c.reference for c in after.components}
                clash.append(f"{a.reference} would overlap {names.get(oid, '?')} (gap {cons.component_gap_mm:g} mm)")
    out.append(
        _result(
            "component_overlap", bool(moved), clash, f"Moved parts keep {cons.component_gap_mm:g} mm from other parts."
        )
    )

    keep: list[str] = []
    polys = keepout_polygons(after)
    for _, a in moved:
        e = extent(a)
        if e is not None and any(
            point_in_polygon(p, poly)
            for poly in polys
            for p in ((e.min_x, e.min_y), (e.max_x, e.max_y), (a.position.x, a.position.y))
        ):
            keep.append(f"{a.reference} would enter a keep-out zone")
    out.append(
        _result("keepout_zones", bool(moved) and bool(polys), keep, "No moved part enters a footprint keep-out.")
    )

    size: list[str] = []
    if ob is not None:
        if cons.max_board_width_mm and ob.width > cons.max_board_width_mm + 1e-6:
            size.append(f"Board width {ob.width:.2f} mm exceeds the {cons.max_board_width_mm:g} mm limit")
        if cons.max_board_height_mm and ob.height > cons.max_board_height_mm + 1e-6:
            size.append(f"Board height {ob.height:.2f} mm exceeds the {cons.max_board_height_mm:g} mm limit")
    out.append(
        _result(
            "board_size",
            bool(cons.max_board_width_mm or cons.max_board_height_mm),
            size,
            "The board is within the size limits.",
        )
    )
    out.append(
        _result(
            "outline_fixed",
            cons.outline_fixed,
            ["The outline is fixed but would change"] if outline_changed else [],
            "The outline is unchanged.",
        )
    )

    rerouting = routed_moves(before, changes)
    if rerouting:
        listed = ", ".join(rerouting[:10]) + ("..." if len(rerouting) > 10 else "")
        out.append(ConstraintResult(id="routed_connectivity", status=ConstraintStatus.UNVERIFIED,
                                    detail=f"Moves routed parts ({listed}): their tracks must be re-routed before connectivity can be verified."))  # fmt: skip
    else:
        out.append(ConstraintResult(id="routed_connectivity", status=ConstraintStatus.NOT_APPLICABLE))

    for r in cons.requirements:
        out.append(ConstraintResult(id=f"requirement:{r.kind}", kind="hard" if r.hard else "soft", status=ConstraintStatus.UNVERIFIED,
                                    detail=(r.description or r.kind) + ": VIA has no evaluator for this requirement, so it is not verified."))  # fmt: skip
    return out
