# ruff: noqa: E501
"""Area analysis, margin analysis and annealing placement on synthetic boards (expected values derived by hand)."""

from __future__ import annotations

import pytest
from via_opt import Constraints, Objective, apply, optimize
from via_opt.algorithms.placement import improve_placement
from via_opt.analysis import area_analysis, margin_analysis
from via_opt.validation import validate

from tests.engineering.synthetic import Board
from via_pcb import parse_pcb
from via_pcb.analysis.profiles import BUILTIN


def design(board: Board):
    return parse_pcb(board.bytes(), filename="s.kicad_pcb")


# ---- area analysis -------------------------------------------------------------------------------------------


def test_area_analysis_measures_the_board():
    # Outline 0..40 x 0..30 (1200 mm²). Two 1 x 1 pads at (5,5) and (15,5): content box 4.5..15.5 x 4.5..5.5.
    d = design(Board().footprint("R1", 5, 5, [{"net": "A"}]).footprint("R2", 15, 5, [{"net": "A"}]))
    a = area_analysis(d)
    assert (
        a["board_width_mm"] == 40 and a["board_height_mm"] == 30 and a["outline_area_mm2"] == 1200 and a["rectangular"]
    )
    assert a["occupied_area_mm2"] == pytest.approx(2.0, abs=0.35)  # grid resolution ~0.17 mm
    assert a["utilisation"] == pytest.approx(2 / 1200, abs=3e-4)
    m = a["unused_margin_mm"]
    assert (m["left"], m["top"], m["right"], m["bottom"]) == (4.5, 4.5, 24.5, 24.5)
    assert any("right side" in o for o in a["observations"]) and any("bottom side" in o for o in a["observations"])
    # Largest empty rectangle: the full-width band below the content, 40 x 24.5 = 980 mm² (the strip to its right is 24.5 x 30 = 735).
    r = a["largest_empty_rectangle"]
    assert r["area_mm2"] == pytest.approx(40 * 24.5, rel=0.01)
    assert len(a["density_grid"]) == 6 and all(len(row) == 6 for row in a["density_grid"])


def test_area_analysis_on_an_empty_board_and_without_an_outline():
    a = area_analysis(design(Board()))
    assert a["available"] and a["component_count"] == 0 and a["occupied_area_mm2"] == 0 and a["utilisation"] == 0
    assert a["largest_empty_rectangle"]["area_mm2"] == pytest.approx(1200, rel=0.01)
    d = design(Board().footprint("R1", 5, 5, [{"net": "A"}]))
    d.outline.bbox = None
    none = area_analysis(d)
    assert none["available"] is False and none["observations"]


# ---- margin analysis ----------------------------------------------------------------------------------------


def test_margin_analysis_separates_violations_from_potential_risks():
    # Profile minimum track 0.15 mm: 0.10 violates; 0.17 passes but is within 25 % (limit 0.1875); 0.30 is fine.
    b = Board().footprint("R1", 5, 5, [{"net": "A"}]).footprint("R2", 15, 5, [{"net": "A"}])
    b.track((5, 5), (10, 5), 0.10, "A").track((5, 8), (10, 8), 0.17, "A").track((5, 11), (10, 11), 0.30, "A")
    d = design(b)
    out = margin_analysis(d, {}, BUILTIN["via-conservative"])
    rule = next(r for r in out["rules"] if r["check"] == "mfg_track_width")
    assert rule["ran"] and rule["violating_features"] == 1 and rule["potential_risk_features"] == 1
    assert rule["limits"] == {"min_track_width": 0.15} and rule["risk_threshold"] == {"min_track_width": 0.1875}
    assert out["violating_features"] >= 1 and any("fabricator" in n for n in out["notes"])


def test_margin_analysis_on_a_clean_board_reports_nothing():
    b = (
        Board()
        .footprint("R1", 5, 5, [{"net": "A"}])
        .footprint("R2", 15, 5, [{"net": "A"}])
        .track((5, 5), (15, 5), 0.5, "A")
    )
    out = margin_analysis(design(b), {}, BUILTIN["via-conservative"])
    track = next(r for r in out["rules"] if r["check"] == "mfg_track_width")
    assert track["violations"] == 0 and track["potential_risk_features"] == 0


# ---- placement ----------------------------------------------------------------------------------------------


def stretched():
    # R2 sits far from R1 on the same net; both unconnected to anything else and not locked.
    return design(Board().footprint("R1", 5, 5, [{"net": "A"}]).footprint("R2", 35, 25, [{"net": "A"}]))


def test_placement_shortens_the_ratsnest_and_reports_its_search():
    d = stretched()
    r = improve_placement(d, Constraints())
    assert r.changes and r.after < r.before
    assert r.before == pytest.approx(((30**2) + (20**2)) ** 0.5)  # hand-derived: straight line between the two pads
    assert r.execution["seed"] and r.execution["iterations"] > 0 and r.execution["budget_exhausted"] is False


def test_placement_is_reproducible_and_never_changes_the_original():
    d = stretched()
    snapshot = d.model_dump_json()
    first, second = improve_placement(d, Constraints()), improve_placement(d, Constraints())
    assert [c.model_dump() for c in first.changes] == [c.model_dump() for c in second.changes]
    assert (first.before, first.after) == (second.before, second.after)
    assert d.model_dump_json() == snapshot


def test_placement_keeps_every_hard_constraint():
    d = design(
        Board()
        .footprint("R1", 5, 5, [{"net": "A"}])
        .footprint("R2", 35, 25, [{"net": "A"}])
        .footprint("R3", 20, 15, [{"net": "A"}])
    )
    cons = Constraints(edge_margin_mm=2.0, component_gap_mm=1.0)
    r = improve_placement(d, cons)
    v, _ = validate(d, r.changes, cons, {})
    assert not v.constraint_violations, v.constraint_violations


def test_fixed_connector_and_locked_parts_never_move():
    d = design(Board().footprint("J1", 5, 5, [{"net": "A"}]).footprint("R2", 35, 25, [{"net": "A"}]))
    r = improve_placement(d, Constraints())
    moved = {ch.target.label for ch in r.changes}
    assert "J1" not in moved and "R2" in moved
    only_fixed = improve_placement(d, Constraints(fixed_components=["R2"]))
    assert only_fixed.changes == []


def test_a_part_is_never_both_moved_and_rotated():
    # Many parts so the search has room to try rotations.
    b = Board()
    for i in range(8):
        b.footprint(f"R{i}", 4 + 4 * i, 4 + (i % 3) * 7, [{"net": "A", "at": (1, 0)}, {"net": f"N{i}", "at": (-1, 0)}])
    d = design(b)
    r = improve_placement(d, Constraints())
    targets = [ch.target.id for ch in r.changes]
    assert len(targets) == len(set(targets))
    again = improve_placement(d, Constraints(allow_rotation=False))
    assert all(ch.kind.value == "move_component" for ch in again.changes)


def test_rotation_can_shorten_a_net_and_the_rotated_design_is_consistent():
    # R2's net-A pad is on its far side (x+3); turning it half a turn brings that pad nearer to R1.
    b = Board().footprint("R1", 5, 5, [{"net": "A", "at": (1, 0)}])
    b.footprint("R2", 12, 5, [{"net": "A", "at": (3, 0)}, {"net": "B", "at": (-3, 0)}])
    b.footprint("R3", 20, 5, [{"net": "B"}])
    d = design(b)
    r = improve_placement(d, Constraints(fixed_components=["R1", "R3"]))
    assert r.after <= r.before
    if r.changes:
        after = apply(d, r.changes)
        assert {c.id for c in after.components} == {c.id for c in d.components}


def test_optimize_offers_a_placement_candidate_with_search_metadata_and_requires_rerouting_when_routed():
    b = (
        Board()
        .footprint("R1", 5, 5, [{"net": "A"}])
        .footprint("R2", 35, 25, [{"net": "A"}])
        .track((5, 5), (35, 25), 0.3, "A")
    )
    res = optimize(design(b), [Objective.PLACEMENT, Objective.AREA, Objective.MANUFACTURABILITY])
    c = next(c for c in res.candidates if c.key == "placement_ratsnest")
    assert (
        c.validation.status.value == "requires_rerouting"
        and c.execution["seed"]
        and c.execution["deterministic"] is True
    )
    assert set(res.analysis) == {"area", "margins"}


def test_margin_analysis_reports_checks_that_were_skipped_instead_of_failing():
    d = design(Board().footprint("R1", 5, 5, [{"net": "A"}]).footprint("R2", 15, 5, [{"net": "A"}]))
    d.outline.graphics, d.outline.bbox, d.outline.closed, d.outline.area = [], None, False, None
    out = margin_analysis(d, {}, BUILTIN["via-conservative"])
    skipped = [r for r in out["rules"] if not r["ran"]]
    assert skipped and all(r["reason"] for r in skipped)
