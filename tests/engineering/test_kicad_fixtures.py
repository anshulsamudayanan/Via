"""Verify parsed output against known, hand-computed values of the source designs.

Fixtures are original VIA works (see fixtures/README.md). Every expected value
below was derived from the source file by hand, not from parser output.
"""

import hashlib
import math
from pathlib import Path

import pytest

from via_pcb import PCBDesign, parse_pcb
from via_pcb.models import LayerKind, PadType, Side

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def ref() -> PCBDesign:
    return parse_pcb(FIXTURES / "via_reference_v8.kicad_pcb")


@pytest.fixture(scope="module")
def legacy() -> PCBDesign:
    return parse_pcb(FIXTURES / "via_legacy_v5.kicad_pcb")


def comp(design: PCBDesign, ref_des: str):
    return next(c for c in design.components if c.reference == ref_des)


class TestReferenceBoardKiCad8:
    def test_source_metadata(self, ref):
        raw = (FIXTURES / "via_reference_v8.kicad_pcb").read_bytes()
        assert ref.source.format == "kicad"
        assert ref.source.format_version == "20240108"
        assert ref.source.generator == "pcbnew"
        assert ref.source.generator_version == "8.0"
        assert ref.source.sha256 == hashlib.sha256(raw).hexdigest()
        assert ref.source.size_bytes == len(raw)
        assert ref.title == "VIA Reference Board"
        assert ref.warnings == []

    def test_board_outline_and_dimensions(self, ref):
        assert ref.outline.closed
        assert len(ref.outline.graphics) == 4
        assert ref.stats.board_width == 50
        assert ref.stats.board_height == 30
        assert ref.stats.board_area == pytest.approx(1500)
        assert (ref.bbox.min_x, ref.bbox.min_y, ref.bbox.max_x, ref.bbox.max_y) == (100, 100, 150, 130)
        assert ref.stats.board_thickness == 1.6

    def test_layers(self, ref):
        copper = [layer for layer in ref.layers if layer.kind == LayerKind.COPPER]
        assert [(c.name, c.side) for c in copper] == [("F.Cu", Side.TOP), ("B.Cu", Side.BOTTOM)]
        by_name = {layer.name: layer for layer in ref.layers}
        assert by_name["F.SilkS"].kind == LayerKind.SILKSCREEN
        assert by_name["F.SilkS"].user_name == "F.Silkscreen"
        assert by_name["Edge.Cuts"].kind == LayerKind.EDGE
        assert by_name["B.CrtYd"].kind == LayerKind.COURTYARD
        assert ref.stats.layer_count == 18
        assert ref.stats.copper_layer_count == 2

    def test_nets(self, ref):
        assert [(n.code, n.name) for n in ref.nets] == [(1, "VCC"), (2, "SIG"), (3, "GND")]
        stats = {s.name: s for s in ref.net_stats}
        assert (stats["VCC"].pad_count, stats["VCC"].track_count, stats["VCC"].via_count) == (2, 3, 0)
        assert stats["VCC"].track_length == pytest.approx(5 + 30.825 + 10)
        assert (stats["SIG"].pad_count, stats["SIG"].track_count, stats["SIG"].via_count) == (2, 4, 1)
        assert stats["SIG"].track_length == pytest.approx(7.175 + math.sqrt(8) + math.pi + 1.775, abs=1e-3)
        assert stats["GND"].track_length == pytest.approx(15)

    def test_components(self, ref):
        assert [c.reference for c in ref.components] == ["R1", "C1", "J1", "H1"]
        r1 = comp(ref, "R1")
        assert (r1.value, r1.footprint) == ("10k", "Resistor_SMD:R_0603_1608Metric")
        assert (r1.position.x, r1.position.y, r1.rotation, r1.side) == (110, 110, 0, Side.TOP)
        assert r1.attributes == ["smd"]
        assert r1.properties["Footprint"] == "Resistor_SMD:R_0603_1608Metric"
        assert "Datasheet" not in r1.properties  # empty properties are dropped

        c1 = comp(ref, "C1")
        assert (c1.value, c1.layer, c1.side, c1.rotation) == ("100nF", "B.Cu", Side.BOTTOM, 90)
        assert ref.stats.components_top == 3
        assert ref.stats.components_bottom == 1

    def test_pads_are_resolved_to_board_coordinates(self, ref):
        r1 = comp(ref, "R1")
        assert [(p.number, p.position.x, p.position.y, p.net) for p in r1.pads] == [
            ("1", 109.175, 110, "VCC"),
            ("2", 110.825, 110, "SIG"),
        ]
        c1 = comp(ref, "C1")  # rotated 90°
        assert [(p.position.x, p.position.y, p.rotation) for p in c1.pads] == [(120, 115.775, 90), (120, 114.225, 90)]
        j1 = comp(ref, "J1")
        assert j1.pads[0].type == PadType.THROUGH_HOLE
        assert j1.pads[0].drill.diameter == 1
        assert set(j1.pads[0].layers) == {"F.Cu", "B.Cu", "F.Mask", "B.Mask"}  # '*.Cu *.Mask' expanded
        h1 = comp(ref, "H1")
        assert h1.pads[0].type == PadType.NPTH and h1.pads[0].net is None
        assert ref.stats.pad_count == 7
        assert (ref.stats.smd_pad_count, ref.stats.through_hole_pad_count) == (4, 2)
        assert ref.stats.unconnected_pad_count == 0

    def test_footprint_graphics(self, ref):
        c1 = comp(ref, "C1")
        courtyard = c1.graphics[0]
        # A rect in a rotated footprint becomes a polygon in board space.
        assert courtyard.kind == "polygon" and courtyard.layer == "B.CrtYd"
        xs = sorted({round(p.x, 3) for p in courtyard.points})
        ys = sorted({round(p.y, 3) for p in courtyard.points})
        assert xs == [119.27, 120.73] and ys == [113.52, 116.48]
        j1_fab = comp(ref, "J1").graphics[0]
        assert j1_fab.kind == "circle" and (j1_fab.points[0].x, j1_fab.points[0].y) == (140, 115)

    def test_tracks_and_vias(self, ref):
        assert ref.stats.track_count == 8
        arcs = [t for t in ref.tracks if t.kind == "arc"]
        assert len(arcs) == 1 and arcs[0].length == pytest.approx(math.pi)
        assert ref.stats.total_track_length == pytest.approx(75.745, abs=1e-3)
        assert ref.stats.min_track_width == 0.25
        assert len(ref.vias) == 1
        via = ref.vias[0]
        assert (via.position.x, via.position.y, via.diameter, via.drill, via.net) == (118, 110, 0.6, 0.3, "SIG")
        assert via.layers == ["F.Cu", "B.Cu"] and via.via_type == "through"

    def test_zones(self, ref):
        assert len(ref.zones) == 1
        zone = ref.zones[0]
        assert (zone.net, zone.layers, zone.filled, zone.keepout) == ("GND", ["B.Cu"], True, False)
        assert zone.area == pytest.approx(48 * 28)

    def test_graphics_exclude_text_and_outline(self, ref):
        assert [(g.kind, g.layer) for g in ref.graphics] == [("circle", "F.SilkS")]

    def test_constraints_only_report_present_fields(self, ref):
        assert ref.constraints.pad_to_mask_clearance == 0.05
        assert ref.constraints.solder_mask_min_width is None
        assert ref.constraints.net_classes == []

    def test_round_trips_through_json(self, ref):
        assert PCBDesign.model_validate_json(ref.model_dump_json()) == ref


class TestLegacyBoardKiCad5:
    def test_header(self, legacy):
        assert legacy.source.format_version == "20171130"
        assert (legacy.source.generator, legacy.source.generator_version) == ("pcbnew", "5.1.12")

    def test_module_with_fp_text(self, legacy):
        r1 = comp(legacy, "R1")
        assert (r1.value, r1.rotation, r1.uuid) == ("4k7", 90, "5F000001")
        assert [(p.position.x, p.position.y) for p in r1.pads] == [(10, 10), (10, 2.38)]
        assert r1.pads[1].drill.slot_length == 1.2
        assert r1.pads[1].net == "Net-(R1-Pad2)"

    def test_unquoted_net_and_layers(self, legacy):
        assert [n.name for n in legacy.nets] == ["GND", "Net-(R1-Pad2)"]
        assert {t.layer for t in legacy.tracks} == {"F.Cu", "B.Cu"}

    def test_outline_with_legacy_arc(self, legacy):
        assert legacy.outline.closed
        assert legacy.stats.board_width == 40 and legacy.stats.board_height == 20
        exact = 40 * 20 - 25 + math.pi * 25 / 4
        assert legacy.stats.board_area == pytest.approx(exact, rel=1e-3)

    def test_net_classes_and_setup(self, legacy):
        assert legacy.constraints.board_thickness == 1.2
        assert legacy.constraints.solder_mask_min_width == 0.25
        (default,) = legacy.constraints.net_classes
        assert (default.name, default.clearance, default.track_width, default.via_drill) == ("Default", 0.2, 0.25, 0.4)
        assert default.nets == ["GND", "Net-(R1-Pad2)"]

    def test_unsupported_objects_are_reported_not_faked(self, legacy):
        codes = [w.code for w in legacy.warnings]
        assert codes == ["unsupported_curve"]
        assert all(g.layer != "F.SilkS" for g in legacy.graphics)
