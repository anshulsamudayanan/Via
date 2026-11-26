"""Placement, routing and electrical checks on synthetic boards (expected values derived by hand)."""

from __future__ import annotations

import math

import pytest

from tests.engineering.synthetic import Board
from via_pcb import parse_pcb
from via_pcb.analysis import CheckStatus, Severity, default_engine
from via_pcb.analysis.checks.routing import ipc2221_width_mm, microstrip_z0, mst_length


def run(board: Board, check: str, **options):
    return default_engine().run(parse_pcb(board.bytes(), filename="s.kicad_pcb"), options=options, only={check})


def test_orientation():
    b = (
        Board()
        .footprint("R1", 10, 10, [{"net": "A"}], rotation=45)
        .footprint("R2", 20, 10, [{"net": "A"}], rotation=270)
    )
    (f,) = run(b, "placement_orientation").findings
    assert f.components == ["R1"] and "45°" in f.description


def test_connector_far_from_edge():
    # Board 40 x 30 -> limit max(5, 3) = 5 mm. J1 pad (1 x 1) at (20, 15): 14.5 mm from the nearest edge.
    b = Board().footprint("J1", 20, 15, [{"net": "A"}]).footprint("J2", 1, 15, [{"net": "A"}])
    (f,) = run(b, "connector_edge_access").findings
    assert f.components == ["J1"]
    assert f.evidence[0].numeric_value == pytest.approx(14.5)


def test_decoupling():
    ic = [{"num": str(n), "at": (n, 0), "net": net} for n, net in ((1, "VCC"), (2, "GND"), (3, "SIG"), (4, "+3V3"))]
    b = Board().footprint("U1", 10, 10, ic)
    b.footprint(
        "C1", 11, 13, [{"num": "1", "net": "VCC"}, {"num": "2", "at": (1, 0), "net": "GND"}]
    )  # 3.0 mm from U1.1
    (f,) = run(b, "decoupling_proximity").findings
    assert f.nets == ["+3V3"] and "no capacitor" in f.description  # VCC is decoupled within 5 mm
    far = (
        Board()
        .footprint("U1", 10, 10, ic)
        .footprint("C1", 30, 10, [{"num": "1", "net": "VCC"}, {"num": "2", "at": (1, 0), "net": "GND"}])
    )
    (f,) = run(far, "decoupling_proximity").findings
    assert {e.label: e.numeric_value for e in f.evidence}["Pin 1 (VCC)"] == pytest.approx(19.0)


def test_board_space():
    # Outline 40 x 30; one 1 x 1 pad at (5, 5) -> right margin 34.5 and bottom 24.5 mm are large.
    (f,) = run(Board().footprint("R1", 5, 5, [{"net": "A"}]), "board_space").findings
    ev = {e.label: e.numeric_value for e in f.evidence}
    assert ev["Right margin"] == pytest.approx(34.5) and ev["Bottom margin"] == pytest.approx(24.5)
    assert ev["Left margin"] == pytest.approx(4.5)


def test_mst_and_detour():
    assert mst_length([(0, 0), (3, 0), (3, 4)]) == pytest.approx(7)
    b = Board().footprint("P1", 5, 10, [{"net": "A"}]).footprint("P2", 15, 10, [{"net": "A"}])
    b.track((5, 10), (5, 20), 0.25, "A").track((5, 20), (15, 20), 0.25, "A").track(
        (15, 20), (15, 10), 0.25, "A"
    )  # 30 mm for a 10 mm gap
    (f,) = run(b, "routing_detour").findings
    assert {e.label: e.numeric_value for e in f.evidence}["Ratio"] == pytest.approx(3.0)
    straight = (
        Board()
        .footprint("P1", 5, 10, [{"net": "A"}])
        .footprint("P2", 15, 10, [{"net": "A"}])
        .track((5, 10), (15, 10), 0.25, "A")
    )
    assert run(straight, "routing_detour").findings == []


def test_ipc2221_formula():
    # 1 A, 10 °C rise, 35 µm outer: A = (1 / (0.048 * 10**0.44)) ** (1/0.725) mil²; width = A / 1.378 mil.
    area = (1 / (0.048 * 10**0.44)) ** (1 / 0.725)
    assert ipc2221_width_mm(1, 10, 0.035, True) == pytest.approx(area / (0.035 / 0.0254) * 0.0254)
    assert ipc2221_width_mm(1, 10, 0.035, False) > ipc2221_width_mm(1, 10, 0.035, True)  # inner layers need more


def test_current_capacity_needs_inputs_and_thickness():
    b = Board().footprint("P1", 5, 10, [{"net": "PWR"}]).track((5, 10), (15, 10), 0.25, "PWR")
    skipped = run(b, "track_current_capacity")
    assert skipped.checks[0].status == CheckStatus.SKIPPED and "No current requirements" in skipped.checks[0].message
    no_thickness = run(b, "track_current_capacity", power={"nets": {"PWR": 2.0}})
    assert no_thickness.findings == [] and no_thickness.checks[0].details["layers_without_copper_thickness"] == ["F.Cu"]
    (f,) = run(b, "track_current_capacity", power={"nets": {"PWR": 2.0}, "copper_thickness_mm": 0.035}).findings
    assert f.severity == Severity.MEDIUM and f.nets == ["PWR"]
    need = ipc2221_width_mm(2.0, 10, 0.035, True)
    assert f.evidence[0].expected == f">= {need:.3f} mm"


def test_microstrip_formula_and_check():
    # IPC-2141: w 0.3, h 0.2, t 0.035, er 4.4.
    z = 87 / math.sqrt(4.4 + 1.41) * math.log(5.98 * 0.2 / (0.8 * 0.3 + 0.035))
    assert microstrip_z0(0.3, 0.2, 0.035, 4.4) == pytest.approx(z)
    # The features fixture's 0.5 mm VBUS track over 0.2 mm dielectric has w/h = 2.5: outside the
    # formula's range, so VIA declines to estimate rather than extrapolate.
    features = parse_pcb(__import__("pathlib").Path(__file__).parent.joinpath("fixtures/via_features_v9.kicad_pcb"))
    refused = default_engine().run(features, options={"impedance": {"nets": {"VBUS": 90}}}, only={"impedance_estimate"})
    assert refused.findings == [] and any("outside" in n for n in refused.checks[0].details["not_estimated"])
    # A 0.3 mm track over the same stackup (w/h = 1.5) is estimated.
    board = Board().footprint("P1", 5, 10, [{"net": "RF"}]).track((5, 10), (15, 10), 0.3, "RF")
    stackup = (
        '(setup (stackup (layer "F.Cu" (type "copper") (thickness 0.035)) '
        '(layer "dielectric 1" (type "core") (thickness 0.2) (material "FR4") (epsilon_r 4.4)) '
        '(layer "B.Cu" (type "copper") (thickness 0.035))) (pad_to_mask_clearance 0))'
    )
    design = parse_pcb(
        board.text().replace("(setup (pad_to_mask_clearance 0))", stackup).encode(), filename="s.kicad_pcb"
    )
    (f,) = (
        default_engine().run(design, options={"impedance": {"nets": {"RF": 75}}}, only={"impedance_estimate"}).findings
    )
    assert f.evidence[0].numeric_value == pytest.approx(round(z, 2))  # ≈ 53 Ω, outside 75 Ω ± 10 %
    near = default_engine().run(design, options={"impedance": {"nets": {"RF": round(z)}}}, only={"impedance_estimate"})
    assert near.findings == []
