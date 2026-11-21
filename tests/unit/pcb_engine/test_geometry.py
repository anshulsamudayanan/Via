import math

import pytest

from via_pcb import geometry as geo


def approx_pt(p, q, tol=1e-9):
    return p[0] == pytest.approx(q[0], abs=tol) and p[1] == pytest.approx(q[1], abs=tol)


def test_rotate_is_ccw_on_y_down_screen():
    # +X rotated 90° CCW on screen points up, i.e. towards -Y in board space.
    assert approx_pt(geo.rotate((1, 0), 90), (0, -1))
    assert approx_pt(geo.rotate((0, 1), 90), (1, 0))
    assert geo.rotate((3, 4), 0) == (3, 4)


def test_to_board_applies_rotation_then_translation():
    assert approx_pt(geo.to_board((-0.775, 0), (120, 115), 90), (120, 115.775))


def test_circle_through_and_arc_length():
    center, r = geo.circle_through((1, 0), (0, 1), (-1, 0))
    assert approx_pt(center, (0, 0)) and r == pytest.approx(1)
    assert geo.arc_length((120, 112), (121, 113), (120, 114)) == pytest.approx(math.pi)
    # Three-quarter arc: the mid point decides the direction.
    assert geo.arc_length((1, 0), (-1, 0), (0, 1)) == pytest.approx(1.5 * math.pi)
    assert geo.circle_through((0, 0), (1, 1), (2, 2)) is None
    assert geo.arc_length((0, 0), (1, 1), (2, 2)) == pytest.approx(math.hypot(2, 2))


def test_legacy_arc_conversion():
    mid, end = geo.arc_mid_from_center((35, 0), (35, 5), 90)
    assert approx_pt(end, (40, 5))
    assert geo.distance(mid, (35, 5)) == pytest.approx(5)


def test_polygon_area_and_bbox():
    assert geo.polygon_area([(0, 0), (4, 0), (4, 3), (0, 3)]) == 12
    assert geo.polygon_area([(0, 0), (1, 1)]) == 0
    b = geo.BBox()
    assert b.empty
    b.extend([(1, 2), (-3, 5)], pad=0.5)
    assert b.as_tuple() == (-3.5, 1.5, 1.5, 5.5)


def test_assemble_outline_chains_segments_in_any_direction():
    edges = [
        geo.OutlineEdge([(0, 0), (10, 0)]),
        geo.OutlineEdge([(10, 5), (10, 0)]),  # reversed
        geo.OutlineEdge([(0, 5), (0, 0)]),
        geo.OutlineEdge([(10, 5), (0, 5)]),
    ]
    result = geo.assemble_outline(edges)
    assert result.closed
    assert result.area == pytest.approx(50)


def test_assemble_outline_reports_open_chains_and_cutouts():
    open_result = geo.assemble_outline([geo.OutlineEdge([(0, 0), (1, 0)]), geo.OutlineEdge([(1, 0), (1, 1)])])
    assert not open_result.closed
    assert open_result.open_chains == 1

    board = geo.OutlineEdge([(0, 0), (10, 0), (10, 10), (0, 10)], closed=True)
    hole = geo.OutlineEdge([(4, 4), (6, 4), (6, 6), (4, 6)], closed=True)
    assert geo.assemble_outline([board, hole]).area == pytest.approx(96)
