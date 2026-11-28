# ruff: noqa: E501
"""Validate a change set by re-running VIA's own checks on the modified design.

KiCad DRC runs on exported files in the follow-up analysis of a change set; here VIA compares its
deterministic findings before and after: any new medium-or-worse problem fails the candidate.
"""

from __future__ import annotations

from typing import Any

from via_opt.candidates import Validation, ValidationStatus
from via_opt.changes import Change, apply
from via_opt.constraints import Constraints
from via_opt.rules import ConstraintStatus, evaluate
from via_pcb.analysis import default_engine
from via_pcb.analysis.checks.manufacturing import MANUFACTURING_CHECKS
from via_pcb.models import PCBDesign

CHECKS = {c.id for c in MANUFACTURING_CHECKS} | {"copper_islands", "board_outline", "board_space"}


def validate(
    design: PCBDesign, changes: list[Change], cons: Constraints, options: dict[str, Any]
) -> tuple[Validation, PCBDesign | None]:
    if any(not ch.exportable for ch in changes):
        return Validation(
            status=ValidationStatus.MANUAL,
            notes=["Includes changes VIA can't apply automatically; make them in KiCad."],
        ), None
    after = apply(design, changes)
    results = evaluate(design, after, changes, cons)
    hard = [r for r in results if r.kind == "hard"]
    broken = [v for r in hard if r.status == ConstraintStatus.VIOLATED for v in r.violations]
    rerouting = any(r.id == "routed_connectivity" and r.status == ConstraintStatus.UNVERIFIED for r in results)
    unverified = [r for r in hard if r.status == ConstraintStatus.UNVERIFIED and r.id != "routed_connectivity"]
    before = default_engine().run(design, options=options, only=CHECKS)
    result = default_engine().run(after, options=options, only=CHECKS)
    old = {f.fingerprint for f in before.findings}
    new = [f for f in result.findings if f.fingerprint not in old and f.severity.rank <= 2]
    resolved = len(old - {f.fingerprint for f in result.findings})
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
    elif unverified:
        status = ValidationStatus.UNVERIFIED
    else:
        status = ValidationStatus.PASSED
    notes += [r.detail for r in results if r.status == ConstraintStatus.UNVERIFIED]
    return Validation(status=status, checks_run=sorted(CHECKS), new_problems=[f"{f.title}: {f.description}"[:300] for f in new[:20]],
                      resolved_problems=resolved, constraint_violations=broken, constraints=results, notes=notes), after  # fmt: skip
