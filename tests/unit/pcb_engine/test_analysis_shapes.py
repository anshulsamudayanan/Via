"""Geometry kernel: distances and pad shapes, checked against hand-computed values."""

from __future__ import annotations

import itertools
import math

import pytest

from via_pcb.analysis.shapes import (
    Grid,
    Owner,
    Shape,
    arc_chords,
    core_distance,
    distance,
    pad_core,
    point_in_polygon,
    segment_segment_distance,
    via_layers,
)
from via_pcb.models import Pad, PadType, Point, Via

OWNER = Owner("track", "t", "t")


def shape(core, r, layer="F.Cu", net="A"):
    return Shape(tuple(core), r, layer, net, OWNER)


def test_segment_distances():
    assert segment_segment_distance((0, 0), (10, 0), (0, 2), (10, 2)) == 2  # parallel
    assert segment_segment_distance((0, 0), (10, 0), (5, -1), (5, 1)) == 0  # crossing
    assert segment_segment_distance((0, 0), (10, 0), (13, 4), (20, 4)) == 5  # endpoint to endpoint: 3-4-5
    assert segment_segment_distance((0, 0), (10, 0), (10, 0), (12, 0)) == 0  # touching


def test_tracks_and_vias():
    a = shape([(0, 0), (10, 0)], 0.125)  # 0.25 mm track
    b = shape([(0, 0.5), (10, 0.5)], 0.125)
    assert distance(a, b) == pytest.approx(0.25)
    via = shape([(5, 1.0)], 0.3)
    assert distance(a, via) == pytest.approx(1.0 - 0.125 - 0.3)
    assert distance(a, shape([(5, 0.2)], 0.3)) == 0  # overlapping


def test_rect_pad_and_point_inside():
    rect = pad_core(
        Pad(number="1", type=PadType.SMD, shape="rect", position=Point(x=0, y=0), size=Point(x=2, y=1), layers=["F.Cu"])
    )
    core, r, approx = rect
    assert r == 0 and not approx
    assert sorted(core) == sorted(((-1, -0.5), (1, -0.5), (1, 0.5), (-1, 0.5)))
    assert core_distance(core, ((0.2, 0.1),)) == 0  # inside
    assert core_distance(core, ((3, 0),)) == pytest.approx(2)


def test_rotated_rect():
    core, _, _ = pad_core(
        Pad(
            number="1",
            type=PadType.SMD,
            shape="rect",
            position=Point(x=10, y=10),
            rotation=90,
            size=Point(x=2, y=1),
            layers=["F.Cu"],
        )
    )
    xs = sorted(round(p[0], 9) for p in core)
    ys = sorted(round(p[1], 9) for p in core)
    assert (xs[0], xs[-1], ys[0], ys[-1]) == (9.5, 10.5, 9.0, 11.0)  # 2x1 turned upright


def test_roundrect_is_exact():
    # 2 x 1 pad, ratio 0.25 -> corner radius 0.25; core is a 1.5 x 0.5 rectangle inflated by 0.25.
    core, r, approx = pad_core(
        Pad(
            number="1",
            type=PadType.SMD,
            shape="roundrect",
            roundrect_ratio=0.25,
            position=Point(x=0, y=0),
            size=Point(x=2, y=1),
            layers=["F.Cu"],
        )
    )
    assert r == pytest.approx(0.25) and not approx
    pad = Shape(core, r, "F.Cu", "A", OWNER)
    # Straight edge: a point 1 mm right of the pad's right edge (x = 1) is 1 mm away.
    assert distance(pad, shape([(2, 0)], 0)) == pytest.approx(1.0)
    # Corner: the rounded corner's centre is (0.75, 0.25); a point on the diagonal 1 mm beyond the arc.
    d = 1 / math.sqrt(2)
    p = (0.75 + (0.25 + 1) * d, 0.25 + (0.25 + 1) * d)
    assert distance(pad, shape([p], 0)) == pytest.approx(1.0)


def test_oval_is_a_stadium():
    core, r, _ = pad_core(
        Pad(
            number="1",
            type=PadType.THROUGH_HOLE,
            shape="oval",
            position=Point(x=0, y=0),
            size=Point(x=1, y=3),
            layers=["F.Cu"],
        )
    )
    assert r == 0.5 and sorted(core) == [(0.0, -1.0), (0.0, 1.0)]


def test_unsupported_shapes_are_flagged():
    for shp in ("trapezoid", "custom", "chamfered_rect"):
        assert pad_core(
            Pad(
                number="1", type=PadType.SMD, shape=shp, position=Point(x=0, y=0), size=Point(x=1, y=1), layers=["F.Cu"]
            )
        )[2]


def test_arc_chords_stay_within_tolerance():
    pts = arc_chords((10, 0), (0, 10), (-10, 0))  # half circle, r = 10
    for p, q in itertools.pairwise(pts):
        mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        assert 10 - math.hypot(*mid) <= 0.002 + 1e-9


def test_point_in_polygon():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon((5, 5), square) and not point_in_polygon((11, 5), square)
    l_shape = [(0, 0), (10, 0), (10, 2), (2, 2), (2, 10), (0, 10)]
    assert point_in_polygon((1, 9), l_shape) and not point_in_polygon((5, 5), l_shape)


def test_via_spans_all_layers_between_its_ends():
    order = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    through = Via(position=Point(x=0, y=0), diameter=0.6, drill=0.3, layers=["F.Cu", "B.Cu"])
    blind = Via(position=Point(x=0, y=0), diameter=0.6, drill=0.3, layers=["F.Cu", "In1.Cu"], via_type="blind")
    assert via_layers(through, order) == order
    assert via_layers(blind, order) == ["F.Cu", "In1.Cu"]


def test_grid_finds_neighbours():
    grid = Grid(cell=1.0)
    grid.insert(0, (0, 0, 0.5, 0.5))
    grid.insert(1, (5, 5, 6, 6))
    assert grid.query((0.6, 0.6, 0.7, 0.7), margin=0.2) == {0}
    assert 1 not in grid.query((0, 0, 1, 1))
