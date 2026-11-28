# ruff: noqa: E501
"""The constraint registry, built-in constraints, lifecycle and weighting (expected values derived by hand)."""

from __future__ import annotations

import pytest
from via_opt import Change, ChangeKind, Constraints, Target
from via_opt.validation import validate

from tests.engineering.synthetic import Board
from via_pcb import parse_pcb


def design(board: Board):
    return parse_pcb(board.bytes(), filename="s.kicad_pcb")


def move(c, x: float, y: float) -> Change:
    return Change(
        kind=ChangeKind.MOVE_COMPONENT,
        target=Target(kind="component", id=c.id or ""),
        before={"x": c.position.x, "y": c.position.y},
        after={"x": x, "y": y},
        reason="t",
    )


def two_resistors():
    # Same net on both, so copper-spacing can't be what rejects the move; only an overlap constraint can.
    return design(Board().footprint("R1", 10, 10, [{"net": "A"}]).footprint("R2", 20, 10, [{"net": "A"}]))


def test_moving_a_part_onto_another_fails_validation():
    d = two_resistors()
    r2 = next(c for c in d.components if c.reference == "R2")
    v, _ = validate(d, [move(r2, 10.5, 10)], Constraints(), {})
    assert v.status.value == "failed"
    assert any("R2" in s and "R1" in s and "overlap" in s for s in v.constraint_violations), v.constraint_violations


def test_moving_a_part_next_to_another_is_fine_but_too_close_to_the_edge_is_not():
    d = two_resistors()  # outline 0..40 x 0..30 (synthetic board)
    r2 = next(c for c in d.components if c.reference == "R2")
    ok, _ = validate(d, [move(r2, 25, 10)], Constraints(), {})
    assert not ok.constraint_violations
    edge, _ = validate(
        d, [move(r2, 0.9, 10)], Constraints(), {}
    )  # pad extent 0.4..1.4: 0.4 mm from the edge, margin is 1
    assert edge.status.value == "failed" and any("from the edge" in v for v in edge.constraint_violations)
    outside, _ = validate(d, [move(r2, -3, 10)], Constraints(), {})
    assert any("past the board outline" in v for v in outside.constraint_violations)


def test_pre_existing_closeness_is_not_blamed_on_a_candidate():
    # R2 already sits 0.4 mm from the edge; moving it along the edge doesn't make that worse.
    d = design(Board().footprint("R1", 10, 10, [{"net": "A"}]).footprint("R2", 0.9, 20, [{"net": "A"}]))
    r2 = next(c for c in d.components if c.reference == "R2")
    v, _ = validate(d, [move(r2, 0.9, 15)], Constraints(), {})
    assert not v.constraint_violations


def result(v, cid):
    return next(r for r in v.constraints if r.id == cid)


def test_an_outline_only_change_stays_validated_and_unrelated_constraints_are_not_applicable():
    from via_opt import Objective, optimize

    b = (
        Board()
        .footprint("R1", 5, 5, [{"net": "A"}])
        .footprint("R2", 15, 5, [{"net": "A"}])
        .track((5, 5), (15, 5), 0.2, "A")
    )
    c = next(c for c in optimize(design(b), [Objective.AREA]).candidates if c.key == "outline_fit")
    assert c.status.value == "validated" and c.validation.status.value == "passed"
    assert result(c.validation, "component_overlap").status.value == "not_applicable"
    assert result(c.validation, "routed_connectivity").status.value == "not_applicable"
    assert result(c.validation, "net_connectivity").status.value == "satisfied"
    assert result(c.validation, "component_identity").status.value == "satisfied"
    assert not [r for r in c.validation.constraints if r.status.value == "unverified"]


def test_a_declared_requirement_via_cannot_check_blocks_validation():
    from via_opt import Objective, Requirement, optimize

    b = (
        Board()
        .footprint("R1", 5, 5, [{"net": "A"}])
        .footprint("R2", 15, 5, [{"net": "A"}])
        .track((5, 5), (15, 5), 0.2, "A")
    )
    cons = Constraints(requirements=[Requirement(kind="impedance_targets", description="50 ohm on A")])
    c = next(c for c in optimize(design(b), [Objective.AREA], cons).candidates if c.key == "outline_fit")
    assert c.validation.status.value == "unverified" and c.status.value == "awaiting_validation"
    r = result(c.validation, "requirement:impedance_targets")
    assert r.status.value == "unverified" and "50 ohm" in r.detail
    # A soft requirement is recorded but doesn't block.
    soft = Constraints(requirements=[Requirement(kind="emc", hard=False)])
    c2 = next(c for c in optimize(design(b), [Objective.AREA], soft).candidates if c.key == "outline_fit")
    assert c2.status.value == "validated" and result(c2.validation, "requirement:emc").kind == "soft"


def test_net_connectivity_is_violated_when_a_pad_changes_net():
    from via_opt.rules import evaluate

    d = two_resistors()
    after = d.model_copy(deep=True)
    after.components[0].pads[0].net = "B"
    r = next(r for r in evaluate(d, after, [], Constraints()) if r.id == "net_connectivity")
    assert r.status.value == "violated"
    gone = d.model_copy(deep=True)
    gone.components.pop()
    assert (
        next(r for r in evaluate(d, gone, [], Constraints()) if r.id == "component_identity").status.value == "violated"
    )


def test_weights_order_candidates_but_never_change_status_or_pareto():
    from via_opt import Objective, optimize

    b = (
        Board()
        .footprint("R1", 5, 5, [{"net": "A"}])
        .footprint("R2", 15, 5, [{"net": "A"}])
        .track((5, 5), (15, 5), 0.2, "A")
    )
    objs = [Objective.AREA, Objective.COST]
    plain = optimize(design(b), objs)
    weighted = optimize(design(b), objs, weights={Objective.AREA: 3.0, Objective.COST: 1.0})
    assert [(c.key, c.status, c.validation.status) for c in plain.candidates] == [
        (c.key, c.status, c.validation.status) for c in weighted.candidates
    ]
    assert plain.pareto == weighted.pareto
    assert all(c.score is None for c in plain.candidates)
    c = next(c for c in weighted.candidates if c.key == "outline_fit")
    # Area 1200 -> 39 (-0.9675); cost index scales with area, so the same relative change: weighted mean -0.9675.
    assert (
        c.score is not None
        and c.score.rank == 1
        and c.score.value == pytest.approx(-0.9675, abs=1e-4)
        and not c.score.partial
    )


def test_a_zero_baseline_is_left_out_and_marks_the_score_partial():
    from via_opt import Candidate, Objective, Validation, ValidationStatus
    from via_opt.ranking import rank

    def cand(key, after, status=ValidationStatus.PASSED):
        return Candidate(key=key, algorithm="a", algorithm_version="1", objectives=[], title="t", summary="s", changes=[],
                         metrics_before={}, metrics_after=after, validation=Validation(status=status), status="validated")  # type: ignore[arg-type]  # fmt: skip

    base = {"board_area_mm2": 100.0, "manufacturing_issues": 0}
    a = cand("a", {"board_area_mm2": 50.0, "manufacturing_issues": 2})
    failed = cand("f", {"board_area_mm2": 10.0, "manufacturing_issues": 0}, ValidationStatus.FAILED)
    rank([a, failed], base, {Objective.AREA: 1.0, Objective.MANUFACTURABILITY: 1.0})
    assert a.score is not None and a.score.value == -0.5 and a.score.partial and a.score.rank == 1
    assert "baseline is 0" in a.score.excluded[0]
    assert failed.score is None  # failed candidates are never ranked


def test_lifecycle_derivation():
    from via_opt import lifecycle

    assert lifecycle("validated", "passed") == "validated"
    assert lifecycle("rejected", "failed") == "validation_failed"
    assert lifecycle("rejected", "failed", "bad idea") == "rejected"
    assert lifecycle("awaiting_validation", "requires_rerouting") == "needs_review"
    assert lifecycle("proposed", "manual") == "needs_review"
    assert lifecycle("accepted", "passed") == "accepted"
    assert lifecycle("accepted", "passed", applied=True) == "applied"


def test_results_are_reproducible_and_the_original_is_never_changed():
    from via_opt import Objective, optimize

    d = design(
        Board()
        .footprint("R1", 5, 5, [{"net": "A"}])
        .footprint("R2", 25, 20, [{"net": "A"}])
        .footprint("J1", 1, 1, [{"net": "A"}])
    )
    snapshot = d.model_dump_json()
    objs = [Objective.AREA, Objective.PLACEMENT, Objective.COST]

    def stable(r):
        data = r.model_dump(mode="json")
        for c in data["candidates"]:
            c.pop("execution")
        return data

    first, second = optimize(d, objs), optimize(d, objs)
    assert stable(first) == stable(second)
    assert all(c.candidate_hash and len(c.candidate_hash) == 64 for c in first.candidates)
    assert [c.candidate_hash for c in first.candidates] == [c.candidate_hash for c in second.candidates]
    assert d.model_dump_json() == snapshot


def test_every_generated_candidate_has_a_declared_module_with_limitations():
    from via_opt import MODULES, Objective, optimize

    assert {m.status for m in MODULES} <= {"implemented", "partial", "planned", "unsupported"}
    assert all(m.preserves for m in MODULES if m.status in ("implemented", "partial") and m.key != "layer_reduction")
    d = design(Board().footprint("R1", 5, 5, [{"net": "A"}]).footprint("R2", 25, 20, [{"net": "A"}]))
    for c in optimize(d, [Objective.AREA, Objective.PLACEMENT]).candidates:
        assert any(m.key == c.key for m in MODULES), c.key
        assert any("KiCad DRC" in s for s in c.limitations)


def test_progress_reports_phases_only():
    from via_opt import Objective, optimize

    seen: list[str] = []
    optimize(
        design(Board().footprint("R1", 5, 5, [{"net": "A"}])),
        [Objective.AREA, Objective.PLACEMENT],
        progress=seen.append,
    )
    assert seen[0] == "Measuring the original design" and seen[-1] == "Comparing candidates" and "Placement" in seen
    assert not any("%" in s for s in seen)
