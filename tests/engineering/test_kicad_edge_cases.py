"""Regression tests for behaviour discovered on real KiCad boards (see docs/ENGINEERING.md)."""

import pytest

from via_pcb import parse_pcb
from via_pcb.models import LayerKind, Side


def board(body: str, layers: str = '(0 "F.Cu" signal) (31 "B.Cu" signal)') -> bytes:
    return f'(kicad_pcb (version 20171130) (layers {layers}) (net 0 "") (net 1 "A") {body})'.encode()


def test_renamed_legacy_copper_layers_are_copper():
    # KiCad 5 allowed renaming copper layers; the real pic_programmer demo uses these names.
    data = board(
        "(module X (layer bottom_layer) (at 10 10) (fp_text reference U1 (at 0 0) (layer B.SilkS))"
        " (pad 1 smd rect (at 0 0) (size 1 1) (layers bottom_layer) (net 1 A)))"
        " (segment (start 0 0) (end 1 0) (width 0.2) (layer top_layer) (net 1))",
        layers="(0 top_layer signal) (1 inner_gnd power) (31 bottom_layer signal) (37 F.SilkS user)",
    )
    design = parse_pcb(data, filename="renamed.kicad_pcb")
    copper = {layer.name: layer.side for layer in design.layers if layer.kind == LayerKind.COPPER}
    assert copper == {"top_layer": Side.TOP, "inner_gnd": Side.INNER, "bottom_layer": Side.BOTTOM}
    assert design.components[0].side == Side.BOTTOM
    assert design.stats.copper_layer_count == 3
    assert design.stats.components_bottom == 1


def test_missing_pad_angle_means_zero_not_footprint_angle():
    # Pad angles are absolute; KiCad omits them when the absolute angle is 0.
    data = board(
        '(footprint "Q" (layer "F.Cu") (at 0 0 -90) (property "Reference" "U1")'
        ' (pad "1" smd rect (at 1 0) (size 1.5 0.3) (layers "F.Cu"))'
        ' (pad "2" smd rect (at 0 1 -90) (size 1.5 0.3) (layers "F.Cu")))'
    )
    design = parse_pcb(data, filename="angles.kicad_pcb")
    comp = design.components[0]
    assert comp.rotation == 270  # normalized to [0, 360)
    assert [p.rotation for p in comp.pads] == [0, 270]
    # Positions still use the footprint rotation: (1, 0) rotated -90° (CW on screen) -> (0, 1).
    assert (comp.pads[0].position.x, comp.pads[0].position.y) == pytest.approx((0, 1))


@pytest.mark.parametrize("raw, expected", [("450", 90), ("-180", 180), ("360", 0), ("-0.5", 359.5)])
def test_angles_are_normalized(raw, expected):
    data = board(f'(footprint "Q" (layer "F.Cu") (at 0 0 {raw}) (property "Reference" "U1"))')
    assert parse_pcb(data, filename="a.kicad_pcb").components[0].rotation == expected
