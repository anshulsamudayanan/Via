# ruff: noqa: E501
"""Validate a change set by re-running VIA's own checks on the modified design.

KiCad DRC re-validation of exported files happens in Milestone 6 (export); here VIA compares its
deterministic findings before and after: any new medium-or-worse problem fails the candidate.
"""

from __future__ import annotations

from typing import Any

from via_opt.candidates import Validation, ValidationStatus
from via_opt.changes import Change, ChangeKind, apply
from via_opt.constraints import Constraints, violations
from via_pcb.analysis import default_engine
from via_pcb.analysis.checks.manufacturing import MANUFACTURING_CHECKS
from via_pcb.models import PCBDesign

CHECKS = {c.id for c in MANUFACTURING_CHECKS} | {"copper_islands", "board_outline", "board_space"}


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


def validate(
    design: PCBDesign, changes: list[Change], cons: Constraints, options: dict[str, Any]
) -> tuple[Validation, PCBDesign | None]:
    if any(not ch.exportable for ch in changes):
        return Validation(
            status=ValidationStatus.MANUAL,
            notes=["Includes changes VIA can't apply automatically; make them in KiCad."],
        ), None
    after = apply(design, changes)
    broken = violations(design, after, cons)
    before = default_engine().run(design, options=options, only=CHECKS)
    result = default_engine().run(after, options=options, only=CHECKS)
    old = {f.fingerprint for f in before.findings}
    new = [f for f in result.findings if f.fingerprint not in old and f.severity.rank <= 2]
    resolved = len(old - {f.fingerprint for f in result.findings})
    rerouting = routed_moves(design, changes)
    notes = []
    if broken:
        status = ValidationStatus.FAILED
    elif rerouting:
        # Moving routed parts leaves their old tracks behind: broken connections and overlaps are
        # expected until re-routing, so they're reported as notes, not as a failed validation.
        status = ValidationStatus.REQUIRES_REROUTING
        if new:
            notes.append(
                f"Until re-routed, VIA sees {len(new)} new problem(s) caused by the moves (listed below); re-run analysis afterwards."
            )
    elif new:
        status = ValidationStatus.FAILED
    else:
        status = ValidationStatus.PASSED
    if rerouting:
        notes.append(f"Moves routed components ({', '.join(rerouting[:10])}{'...' if len(rerouting) > 10 else ''}): "
                     "their tracks must be re-routed, so connectivity can't be validated until then.")  # fmt: skip
    return Validation(status=status, checks_run=sorted(CHECKS), new_problems=[f"{f.title}: {f.description}"[:300] for f in new[:20]],
                      resolved_problems=resolved, constraint_violations=broken, notes=notes), after  # fmt: skip
