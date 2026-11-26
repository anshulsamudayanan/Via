"""VIA Optimize on synthetic boards (expected values derived by hand)."""

from __future__ import annotations

import pytest
from via_opt import (
    Candidate,
    CandidateStatus,
    Change,
    ChangeKind,
    Constraints,
    Objective,
    Target,
    ValidationStatus,
    apply,
    dominates,
    optimize,
    pareto_front,
)

from tests.engineering.synthetic import Board
from via_pcb import parse_pcb


def design(board: Board):
    return parse_pcb(board.bytes(), filename="s.kicad_pcb")


def by_key(result) -> dict[str, Candidate]:
    return {c.key: c for c in result.candidates}


def test_apply_moves_pads_and_never_mutates_the_original():
    d = design(Board().footprint("R1", 10, 10, [{"net": "A", "at": (1, 0)}]))
    r1 = d.components[0]
    moved = apply(
        d,
        [
            Change(
                kind=ChangeKind.MOVE_COMPONENT,
                target=Target(kind="component", id=r1.id),
                before={"x": 10, "y": 10},
                after={"x": 15, "y": 12},
                reason="t",
            )
        ],
    )
    assert (moved.components[0].pads[0].position.x, moved.components[0].pads[0].position.y) == (16.0, 12.0)
    assert (d.components[0].pads[0].position.x, d.components[0].pads[0].position.y) == (11.0, 10.0)  # untouched
    turned = apply(
        d,
        [
            Change(
                kind=ChangeKind.ROTATE_COMPONENT,
                target=Target(kind="component", id=r1.id),
                before={"rotation": 0},
                after={"rotation": 90},
                reason="t",
            )
        ],
    )
    p = turned.components[0].pads[0].position
    assert (round(p.x, 9), round(p.y, 9)) == (10.0, 9.0)  # (1, 0) turned 90° CCW on a Y-down screen -> (0, -1)


def test_outline_fit_shrinks_to_content_plus_margin():
    # Outline 0..40 x 0..30; one 1 x 1 pad at (5, 5) and a track to (15, 5) (width 0.2).
    b = (
        Board()
        .footprint("R1", 5, 5, [{"net": "A"}])
        .footprint("R2", 15, 5, [{"net": "A"}])
        .track((5, 5), (15, 5), 0.2, "A")
    )
    result = optimize(design(b), [Objective.AREA])
    c = by_key(result)["outline_fit"]
    # Content: pads 4.5..15.5 x 4.5..5.5; margin max(1.0, 0.3) = 1 mm -> 3.5..16.5 x 3.5..6.5.
    assert c.changes[0].after == {"min_x": 3.5, "min_y": 3.5, "max_x": 16.5, "max_y": 6.5}
    assert c.metrics_after["board_area_mm2"] == pytest.approx(13 * 3)
    assert c.status == CandidateStatus.VALIDATED and c.validation.status == ValidationStatus.PASSED
    assert any("board area: 1200" in b for b in c.expected_benefits)
    assert result.pareto == ["outline_fit"]


def test_outline_fixed_constraint_is_respected():
    b = Board().footprint("R1", 5, 5, [{"net": "A"}])
    result = optimize(design(b), [Objective.AREA], Constraints(outline_fixed=True))
    assert result.candidates == [] and "fixed" in result.notes[0]


def test_via_standardization_only_touches_failing_vias_and_respects_clearance():
    # Profile: drill 0.3, via 0.6, ring 0.15. Via A fails (0.5/0.25); via B passes (0.889/0.4).
    b = Board().via((10, 10), 0.5, 0.25, "A").via((20, 10), 0.889, 0.4, "B")
    c = by_key(optimize(design(b), [Objective.MANUFACTURABILITY]))["via_standardization"]
    (change,) = c.changes
    assert change.after == {"diameter": 0.6, "drill": 0.3}  # drill -> 0.3, diameter -> max(0.6, 0.3 + 0.3)
    assert c.status == CandidateStatus.VALIDATED
    # A track of another net 0.5 mm from the via centre: growing to r = 0.3 leaves 0.5 - 0.3 - 0.1 = 0.1 < 0.15.
    blocked = Board().via((10, 10), 0.5, 0.25, "A").track((5, 10.5), (15, 10.5), 0.2, "B")
    result = optimize(design(blocked), [Objective.MANUFACTURABILITY])
    assert "via_standardization" not in by_key(result) and any("can't grow" in n for n in result.notes)


def test_track_widening_stops_at_clearance():
    # 0.1 mm track of A at y=10 next to a 0.2 mm track of B at y=10.5: centre gap 0.5.
    # Max half-width for A: 0.5 - 0.1 (B half) - 0.15 (clearance) = 0.25 -> width 0.5 > target 0.15, so target reached.
    b = Board().track((5, 10), (15, 10), 0.1, "A").track((5, 10.5), (15, 10.5), 0.2, "B")
    c = by_key(optimize(design(b), [Objective.MANUFACTURABILITY]))["track_min_width"]
    assert [ch.after["width"] for ch in c.changes] == [0.15]
    # Tighter: B at y=10.3 -> half-width room 0.3 - 0.1 - 0.15 = 0.05 -> width 0.1: no growth possible.
    tight = Board().track((5, 10), (15, 10), 0.1, "A").track((5, 10.3), (15, 10.3), 0.2, "B")
    assert "track_min_width" not in by_key(optimize(design(tight), [Objective.MANUFACTURABILITY]))


def test_power_widening_needs_inputs():
    b = Board().footprint("P1", 5, 10, [{"net": "PWR"}]).track((5, 10), (15, 10), 0.25, "PWR")
    result = optimize(design(b), [Objective.THERMAL])
    assert result.candidates == [] and "current requirements" in result.notes[0]
    result = optimize(
        design(b), [Objective.THERMAL], options={"power": {"nets": {"PWR": 1.0}, "copper_thickness_mm": 0.035}}
    )
    c = by_key(result)["power_track_widening"]
    assert c.changes[0].after["width"] > 0.25 and c.status == CandidateStatus.VALIDATED


def test_placement_moves_respect_fixed_parts_and_need_rerouting():
    # R1 and R2 share net A but sit 20 mm apart; J1 (a connector) is fixed by default.
    b = (Board().footprint("R1", 5, 15, [{"net": "A"}]).footprint("R2", 25, 15, [{"net": "A"}])
         .footprint("J1", 35, 15, [{"net": "A"}]).track((5, 15), (25, 15), 0.25, "A"))  # fmt: skip
    c = by_key(optimize(design(b), [Objective.PLACEMENT]))["placement_ratsnest"]
    moved = {ch.target.label for ch in c.changes}
    assert "J1" not in moved and moved
    assert (
        c.status == CandidateStatus.AWAITING_VALIDATION and c.validation.status == ValidationStatus.REQUIRES_REROUTING
    )
    assert c.metrics_after["ratsnest_mm"] < c.metrics_before["ratsnest_mm"]
    # With every part fixed, nothing moves.
    none = optimize(design(b), [Objective.PLACEMENT], Constraints(fixed_components=["R1", "R2"]))
    assert "placement_ratsnest" not in by_key(none)


def test_layer_reduction_is_a_manual_proposal():
    b = (
        Board(copper=("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"))
        .footprint("R1", 5, 5, [{"net": "A"}])
        .footprint("R2", 15, 5, [{"net": "A"}])
    )
    b.track((5, 5), (15, 5), 0.25, "A").track((5, 6), (15, 6), 0.25, "A", layer="B.Cu")
    c = by_key(optimize(design(b), [Objective.LAYERS]))["layer_reduction"]
    assert c.changes[0].after == {"count": 2} and c.validation.status == ValidationStatus.MANUAL
    assert c.status == CandidateStatus.PROPOSED and not c.changes[0].exportable


def test_pareto():
    a = {"area": 10.0, "cost": 5.0}
    b = {"area": 12.0, "cost": 4.0}
    c = {"area": 12.0, "cost": 6.0}  # dominated by a
    assert dominates(a, c, ["area", "cost"]) and not dominates(a, b, ["area", "cost"])
    assert sorted(pareto_front({"a": a, "b": b, "c": c}, ["area", "cost"])) == ["a", "b"]
    assert pareto_front({"a": {"area": None}, "b": {"area": 1.0}}, ["area"]) == [
        "a",
        "b",
    ]  # missing values aren't compared


def test_constraint_violations_fail_validation():
    from via_opt.validation import validate

    d = design(Board().footprint("J1", 10, 10, [{"net": "A"}]))
    j1 = d.components[0]
    v, _ = validate(
        d,
        [
            Change(
                kind=ChangeKind.MOVE_COMPONENT,
                target=Target(kind="component", id=j1.id),
                before={"x": 10, "y": 10},
                after={"x": 12, "y": 10},
                reason="t",
            )
        ],
        Constraints(),
        {},
    )
    assert v.status == ValidationStatus.FAILED and "J1 is fixed" in v.constraint_violations[0]
