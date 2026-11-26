# ruff: noqa: E501  (board-building test data)
"""Connectivity and manufacturing checks on synthetic boards (expected values derived by hand).

Profile used unless stated: VIA conservative (track 0.15, clearance 0.15, drill 0.3, via 0.6,
annular ring 0.15, hole-to-hole 0.5, copper-to-edge 0.3, silkscreen 0.15 mm).
"""

from __future__ import annotations

import pytest

from tests.engineering.synthetic import Board
from via_pcb import parse_pcb
from via_pcb.analysis import CheckStatus, Severity, Verification, default_engine
from via_pcb.analysis.profiles import BUILTIN


def run(board: Board, *checks: str, **options):
    design = parse_pcb(board.bytes(), filename="synthetic.kicad_pcb")
    return default_engine().run(design, options=options, only=set(checks))


def findings(board: Board, check: str, **options):
    return run(board, check, **options).findings


def two_pads(net: str = "A") -> Board:
    # P1 pad at (10, 10), P2 pad at (20, 10), both 1 x 1 mm SMD on F.Cu.
    return Board().footprint("P1", 10, 10, [{"net": net}]).footprint("P2", 20, 10, [{"net": net}])


# --- copper islands ----------------------------------------------------------------------------


def test_routed_net_is_connected():
    assert findings(two_pads().track((10, 10), (20, 10), 0.25, "A"), "copper_islands") == []


def test_half_routed_net_reports_two_groups_and_the_gap():
    (f,) = findings(two_pads().track((10, 10), (15, 10), 0.25, "A"), "copper_islands")
    assert (f.rule, f.severity, f.verification) == ("net_not_connected", Severity.HIGH, Verification.VERIFIED)
    assert f.nets == ["A"] and f.components == ["P1", "P2"]
    ev = {e.label: e for e in f.evidence}
    assert ev["Copper groups"].numeric_value == 2
    assert ev["Shortest missing connection"].numeric_value == pytest.approx(10.0)  # pad centre to pad centre
    assert sorted((p.x, p.y) for p in f.region.points) == [(10.0, 10.0), (20.0, 10.0)]


def test_t_junction_and_via_layer_change_connect():
    # P1-(F.Cu)-(15,10); a branch from the middle of that track up to the via at (12,5);
    # the via drops to B.Cu, which runs to (20,5) and then down to P2 (a through-hole pad).
    board = (
        Board()
        .footprint("P1", 10, 10, [{"net": "A"}])
        .footprint(
            "P2", 20, 10, [{"net": "A", "type": "thru_hole", "shape": "circle", "size": (1.6, 1.6), "drill": 0.8}]
        )
        .track((10, 10), (15, 10), 0.25, "A")
        .track((12, 10), (12, 5), 0.25, "A")  # starts mid-track: a T-junction
        .via((12, 5), 0.6, 0.3, "A")
        .track((12, 5), (20, 5), 0.25, "A", layer="B.Cu")
        .track((20, 5), (20, 10), 0.25, "A", layer="B.Cu")
    )
    assert findings(board, "copper_islands") == []


def test_tracks_on_different_layers_dont_connect_without_a_via():
    board = two_pads().track((10, 10), (15, 10), 0.25, "A").track((15, 10), (20, 10), 0.25, "A", layer="B.Cu")
    assert len(findings(board, "copper_islands")) == 1


def test_zone_outline_connects_pads_but_is_marked_approximate():
    tht = {"type": "thru_hole", "shape": "circle", "size": (1.6, 1.6), "drill": 0.8, "net": "GND"}
    board = Board().footprint("J1", 10, 10, [tht]).footprint("J2", 20, 10, [tht])
    board.zone("GND", "B.Cu", [(5, 5), (25, 5), (25, 15), (5, 15)])
    assert findings(board, "copper_islands") == []
    # Shrink the zone so it misses J2: still split, reported as an approximation.
    board2 = Board().footprint("J1", 10, 10, [tht]).footprint("J2", 20, 10, [tht])
    board2.zone("GND", "B.Cu", [(5, 5), (15, 5), (15, 15), (5, 15)])
    (f,) = findings(board2, "copper_islands")
    assert (f.severity, f.verification) == (Severity.MEDIUM, Verification.HEURISTIC)
    assert "zone" in f.explanation


def test_islands_check_defers_to_kicad_drc():
    board = two_pads().track((10, 10), (15, 10), 0.25, "A")
    result = run(board, "copper_islands", kicad_drc={"report": {"violations": []}, "rules": "project_file"})
    assert result.checks[0].status == CheckStatus.SKIPPED and "KiCad DRC ran" in result.checks[0].message


# --- single-pad nets and layer usage --------------------------------------------------------------


def test_single_pad_nets():
    board = Board().footprint(
        "U1", 10, 10, [{"num": "1", "net": "SENSE"}, {"num": "3", "at": (2, 0), "net": "unconnected-(U1-Pad3)"}]
    )
    (f,) = findings(board, "single_pad_nets")
    assert f.nets == ["SENSE"] and [o.label for o in f.objects] == ["SENSE", "U1 pad 1"]


def test_unused_inner_layer():
    board = Board(copper=("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"))
    board.footprint(
        "J1", 10, 10, [{"type": "thru_hole", "shape": "circle", "size": (1.6, 1.6), "drill": 0.8, "net": "GND"}]
    )
    board.zone("GND", "In1.Cu", [(5, 5), (25, 5), (25, 15), (5, 15)])
    board.track((10, 10), (20, 10), 0.25, "GND")
    result = run(board, "copper_layer_usage")
    # F.Cu has a track and In1.Cu a zone; In2.Cu and B.Cu only see the through-hole pad.
    assert {f.objects[0].id for f in result.findings} == {"In2.Cu", "B.Cu"}
    assert result.checks[0].details["In1.Cu"]["zones"] == 1


# --- manufacturing ---------------------------------------------------------------------------------


def test_track_width():
    board = two_pads().track((10, 10), (15, 10), 0.1, "A").track((15, 10), (20, 10), 0.15, "A")
    (f,) = findings(board, "mfg_track_width")
    assert f.nets == ["A"] and len(f.objects) == 1  # 0.15 equals the minimum: allowed
    assert {e.label: e.numeric_value for e in f.evidence}["Narrowest track"] == 0.1
    assert any("VIA conservative" in e.label for e in f.evidence)
    # A profile that allows 0.1 mm: nothing to report.
    custom = BUILTIN["via-advanced"].model_dump()
    assert findings(board, "mfg_track_width", manufacturing_profile=custom) == []


def test_vias():
    board = Board().via((10, 10), 0.5, 0.2, "A")  # drill 0.2 < 0.3, diameter 0.5 < 0.6, ring 0.15 = 0.15
    rules = sorted(f.rule for f in findings(board, "mfg_vias"))
    assert rules == ["via_drill_too_small", "via_too_small"]


def test_pad_annular_ring_and_drill():
    board = Board().footprint("J1", 10, 10, [
        {"num": "1", "type": "thru_hole", "shape": "circle", "size": (1.0, 1.0), "drill": 0.8, "net": "A"},  # ring 0.1
        {"num": "2", "at": (3, 0), "type": "thru_hole", "shape": "circle", "size": (1.6, 1.6), "drill": 0.25, "net": "B"},  # drill 0.25
    ])  # fmt: skip
    by_rule = {f.rule: f for f in findings(board, "mfg_pad_holes")}
    assert set(by_rule) == {"pad_annular_ring_too_small", "pad_drill_too_small"}
    assert {e.label: e.numeric_value for e in by_rule["pad_annular_ring_too_small"].evidence}[
        "Narrowest annular ring"
    ] == pytest.approx(0.1)
    assert [o.label for o in by_rule["pad_drill_too_small"].objects] == ["J1 pad 2"]


def test_hole_spacing():
    ok = Board().via((10, 10), 0.8, 0.4, "A").via((10.9, 10), 0.8, 0.4, "B")  # edge gap 0.9 - 0.4 = 0.5
    assert findings(ok, "mfg_hole_spacing") == []
    close = Board().via((10, 10), 0.8, 0.4, "A").via((10.8, 10), 0.8, 0.4, "B")  # 0.4 < 0.5
    (f,) = findings(close, "mfg_hole_spacing")
    assert {e.label: e.numeric_value for e in f.evidence}["Hole edge to hole edge"] == pytest.approx(0.4)


def test_copper_to_edge():
    # Outline (0,0)-(40,30). Track along y = 0.2, width 0.2: copper edge at 0.1 mm from the board edge.
    board = two_pads().track((5, 0.2), (30, 0.2), 0.2, "A")
    (f,) = findings(board, "mfg_copper_to_edge")
    assert f.nets == ["A"] and {e.label: e.numeric_value for e in f.evidence}[
        "Closest copper to edge"
    ] == pytest.approx(0.1)
    assert findings(two_pads(), "mfg_copper_to_edge") == []


def test_copper_spacing_between_nets():
    # Parallel 0.25 mm tracks 0.35 mm apart centre to centre: 0.1 mm gap (< 0.15).
    board = Board().track((5, 10), (15, 10), 0.25, "A").track((5, 10.35), (15, 10.35), 0.25, "B")
    (f,) = findings(board, "mfg_copper_spacing")
    assert (f.severity, f.nets) == (Severity.HIGH, ["A", "B"])
    assert {e.label: e.numeric_value for e in f.evidence}["Smallest gap"] == pytest.approx(0.1)
    # Same net at the same distance isn't a spacing problem; 0.4 mm apart (0.15 gap) is allowed.
    assert (
        findings(
            Board().track((5, 10), (15, 10), 0.25, "A").track((5, 10.35), (15, 10.35), 0.25, "A"), "mfg_copper_spacing"
        )
        == []
    )
    assert (
        findings(
            Board().track((5, 10), (15, 10), 0.25, "A").track((5, 10.4), (15, 10.4), 0.25, "B"), "mfg_copper_spacing"
        )
        == []
    )


def test_roundrect_corners_are_measured_exactly():
    # Two 1 x 1 roundrect pads (ratio 0.25 -> corner radius 0.25) placed diagonally with corners facing.
    # Their bounding squares' corners are 0.1 mm apart along x and y (0.141 diagonal); the rounded
    # corners are much farther: centres of the corner arcs are (0.25+0.1/2)... computed below.
    import math

    board = Board().footprint("A1", 10, 10, [{"shape": "roundrect", "rr": 0.25, "net": "A"}])
    board.footprint("B1", 11.1, 11.1, [{"shape": "roundrect", "rr": 0.25, "net": "B"}])
    arc_a, arc_b = (10.25, 10.25), (10.85, 10.85)  # corner-arc centres (pad centre ± 0.25)
    expected = math.dist(arc_a, arc_b) - 0.5
    assert expected > 0.15  # rounded corners: no violation, though the square corners are 0.141 apart
    assert findings(board, "mfg_copper_spacing") == []


def test_silkscreen_width_grouped_by_layer_and_width():
    board = (
        Board()
        .footprint("R1", 10, 10, [{"net": "A"}], silk_width=0.12)
        .footprint("R2", 20, 10, [{"net": "A"}], silk_width=0.12)
    )
    board.footprint("R3", 30, 10, [{"net": "A"}], silk_width=0.15)
    (f,) = findings(board, "mfg_silkscreen")
    assert f.components == ["R1", "R2"] and f.severity == Severity.LOW


# --- Real boards: VIA must agree with KiCad where KiCad is authoritative ---------------------

REAL = __import__("pathlib").Path(__file__).parent / "real"


@pytest.mark.parametrize("tag", ["6.0.11", "7.0.11", "8.0.8", "9.0.0"])
@pytest.mark.parametrize("project", ["video", "pic_programmer"])
def test_no_false_positives_on_kicad_clean_real_boards(project, tag):
    """KiCad 9 DRC with the project rules reports no clearance or unconnected items on these boards,
    and both net classes require 0.2 mm. VIA's spacing (at 0.2 mm) and islands checks must agree."""
    path = REAL / f"{project}_{tag}.kicad_pcb"
    if not path.exists():
        pytest.skip("real boards not fetched (scripts/fetch_real_fixtures.py)")
    design = parse_pcb(path)
    profile = {**BUILTIN["via-conservative"].model_dump(), "key": "netclass", "min_clearance": 0.2}
    result = default_engine().run(
        design, options={"manufacturing_profile": profile}, only={"mfg_copper_spacing", "copper_islands"}
    )
    assert result.findings == []
