import math

import pytest

from su_mcp_bridge.core import units


def test_mm_inch_round_trip():
    for v in [0.0, 1.0, 25.4, 1000.0, -3000.0, 12345.678]:
        assert math.isclose(units.in_to_mm(units.mm_to_in(v)), v, rel_tol=1e-12)


def test_mm_to_in_exact_for_inch():
    assert math.isclose(units.mm_to_in(25.4), 1.0, rel_tol=1e-15)


def test_point_round_trip_2d_3d():
    pt2 = [1000.0, 2540.0]
    pt3 = [1000.0, 2540.0, 100.0]
    assert units.point_in_to_mm(units.point_mm_to_in(pt2)) == pytest.approx(pt2)
    assert units.point_in_to_mm(units.point_mm_to_in(pt3)) == pytest.approx(pt3)


def test_polygon_round_trip():
    poly_mm = [[0, 0], [3000, 0], [3000, 4000], [0, 4000]]
    out = units.polygon_in_to_mm(units.polygon_mm_to_in(poly_mm))
    for a, b in zip(poly_mm, out):
        assert a == pytest.approx(b, rel=1e-12)


def test_feet_inches_round_trip():
    # 5ft 6in = 66 in = 1676.4 mm
    mm = units.feet_inches_to_mm(5, 6)
    assert math.isclose(mm, 1676.4, rel_tol=1e-12)
    feet, inches = units.mm_to_feet_inches(mm)
    assert feet == 5
    assert math.isclose(inches, 6.0, rel_tol=1e-12)
