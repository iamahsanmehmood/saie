import math

import pytest

from su_mcp_bridge.core import geometry as G


# --------------------------------------------------------------------------
# Walls / segments
# --------------------------------------------------------------------------


def test_wall_length_axis_aligned():
    assert G.wall_length_mm([[0, 0], [3000, 0]]) == pytest.approx(3000.0)
    assert G.wall_length_mm([[0, 0], [0, 4000]]) == pytest.approx(4000.0)


def test_wall_length_diagonal():
    # 3-4-5 triangle
    assert G.wall_length_mm([[0, 0], [3000, 4000]]) == pytest.approx(5000.0)


def test_wall_length_invalid_centerline():
    with pytest.raises(ValueError):
        G.wall_length_mm([[0, 0]])


def test_wall_unit_vector_diagonal():
    ux, uy = G.wall_unit_vector([[0, 0], [3000, 4000]])
    assert math.isclose(ux, 0.6, rel_tol=1e-12)
    assert math.isclose(uy, 0.8, rel_tol=1e-12)


def test_wall_perpendicular_orthogonal_to_centerline():
    centerline = [[0, 0], [1000, 1000]]
    ux, uy = G.wall_unit_vector(centerline)
    px, py = G.wall_perpendicular(centerline)
    assert math.isclose(ux * px + uy * py, 0.0, abs_tol=1e-12)


def test_wall_axis_aligned_classification():
    assert G.wall_axis_aligned([[0, 0], [3000, 0]]) == "x"
    assert G.wall_axis_aligned([[0, 0], [0, 3000]]) == "y"
    # 45-degree -> diagonal, not "x" or "y"
    assert G.wall_axis_aligned([[0, 0], [3000, 3000]]) == "diag"
    # Just-barely diagonal (5deg off X) should be diagonal
    assert G.wall_axis_aligned([[0, 0], [3000, 263]]) == "diag"


def test_miter_angle_perpendicular_walls():
    a = [[0, 0], [3000, 0]]
    b = [[3000, 0], [3000, 3000]]
    # Both vectors point AWAY from the shared corner: (1,0) and (0,1) -> 90 deg.
    assert G.miter_angle_deg(a, b) == pytest.approx(90.0, abs=1e-9)


def test_miter_angle_collinear_walls():
    a = [[0, 0], [3000, 0]]
    b = [[3000, 0], [6000, 0]]
    # Both pointing +x -> angle 0.
    assert G.miter_angle_deg(a, b) == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------
# Polygons
# --------------------------------------------------------------------------


def test_polygon_area_unit_square():
    sq = [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]
    assert G.polygon_area_mm(sq) == pytest.approx(1_000_000.0)
    assert G.polygon_is_ccw(sq) is True


def test_polygon_area_negative_when_clockwise():
    cw = [[0, 0], [0, 1000], [1000, 1000], [1000, 0]]
    assert G.polygon_area_mm(cw) == pytest.approx(-1_000_000.0)
    assert G.polygon_is_ccw(cw) is False


def test_polygon_centroid_unit_square():
    sq = [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]
    cx, cy = G.polygon_centroid_mm(sq)
    assert cx == pytest.approx(500.0)
    assert cy == pytest.approx(500.0)


def test_point_in_polygon_basics():
    sq = [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]
    assert G.point_in_polygon_mm([500, 500], sq) is True
    assert G.point_in_polygon_mm([1500, 500], sq) is False
    assert G.point_in_polygon_mm([-1, 500], sq) is False


def test_polygon_is_simple_convex_quadrilateral():
    sq = [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]
    assert G.polygon_is_simple(sq) is True


def test_polygon_is_simple_self_intersecting_bowtie():
    bowtie = [[0, 0], [1000, 1000], [1000, 0], [0, 1000]]
    assert G.polygon_is_simple(bowtie) is False


def test_points_coincident_within_tolerance():
    assert G.points_coincident_mm([0, 0], [0.5, 0.5], tolerance_mm=1.0)
    assert not G.points_coincident_mm([0, 0], [10, 0], tolerance_mm=1.0)


def test_bounding_box_basic():
    poly = [[0, 0], [3000, 0], [3000, 4000], [0, 4000]]
    assert G.bounding_box_mm(poly) == (0, 0, 3000, 4000)
