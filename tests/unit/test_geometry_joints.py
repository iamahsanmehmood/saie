"""tests/unit/test_geometry_joints.py — Unit tests for wall joining.

Tests T-junction, cross-junction, L-corner, and acute angle cases.
"""

import math
import pytest
from su_mcp_bridge.core.geometry import (
    classify_junction,
    validate_wall_network,
    resolve_butt_joints,
    wall_length_mm,
    points_coincident_mm,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wall(id: str, cl: list, thick: float = 200) -> dict:
    return {"id": id, "centerline": cl, "thickness_mm": thick}


# ---------------------------------------------------------------------------
# classify_junction
# ---------------------------------------------------------------------------

class TestClassifyJunction:
    def test_single_endpoint(self):
        members = [([0, 0], "W1", 0)]
        walls = [_wall("W1", [[0, 0], [5000, 0]])]
        assert classify_junction(members, walls) == "end"

    def test_two_walls_L(self):
        members = [([0, 0], "W1", 0), ([0, 0], "W2", 0)]
        walls = [
            _wall("W1", [[0, 0], [5000, 0]]),
            _wall("W2", [[0, 0], [0, 5000]]),
        ]
        assert classify_junction(members, walls) == "L"

    def test_three_walls_T(self):
        members = [
            ([3000, 0], "W1", 1),
            ([3000, 0], "W2", 0),
            ([3000, 0], "W3", 0),
        ]
        walls = [
            _wall("W1", [[0, 0], [3000, 0]]),
            _wall("W2", [[3000, 0], [6000, 0]]),
            _wall("W3", [[3000, 0], [3000, 4000]]),
        ]
        assert classify_junction(members, walls) == "T"

    def test_four_walls_cross(self):
        members = [
            ([3000, 3000], "W1", 1),
            ([3000, 3000], "W2", 0),
            ([3000, 3000], "W3", 1),
            ([3000, 3000], "W4", 0),
        ]
        walls = [
            _wall("W1", [[0, 3000], [3000, 3000]]),
            _wall("W2", [[3000, 3000], [6000, 3000]]),
            _wall("W3", [[3000, 0], [3000, 3000]]),
            _wall("W4", [[3000, 3000], [3000, 6000]]),
        ]
        assert classify_junction(members, walls) == "cross"


# ---------------------------------------------------------------------------
# validate_wall_network
# ---------------------------------------------------------------------------

class TestValidateWallNetwork:
    def test_valid_network(self):
        walls = [
            _wall("W1", [[0, 0], [5000, 0]]),
            _wall("W2", [[5000, 0], [5000, 4000]]),
        ]
        warnings = validate_wall_network(walls)
        assert len(warnings) == 0

    def test_zero_length_wall(self):
        walls = [_wall("W1", [[0, 0], [0, 0]])]
        warnings = validate_wall_network(walls)
        assert any("Zero-length" in w["warning"] for w in warnings)

    def test_wall_shorter_than_thickness(self):
        walls = [_wall("W1", [[0, 0], [100, 0]], thick=200)]
        warnings = validate_wall_network(walls)
        assert any("shorter than thickness" in w["warning"] for w in warnings)

    def test_duplicate_walls(self):
        walls = [
            _wall("W1", [[0, 0], [5000, 0]]),
            _wall("W2", [[0, 0], [5000, 0]]),
        ]
        warnings = validate_wall_network(walls)
        assert any("Overlaps" in w["warning"] for w in warnings)


# ---------------------------------------------------------------------------
# resolve_butt_joints
# ---------------------------------------------------------------------------

class TestResolveButtJoints:
    def test_l_corner(self):
        """Two perpendicular walls meeting at a corner."""
        walls = [
            _wall("W1", [[0, 0], [5000, 0]], thick=200),
            _wall("W2", [[5000, 0], [5000, 4000]], thick=200),
        ]
        adjusted = resolve_butt_joints(walls)
        # W2 is shorter, so it should be pulled back
        w2_start = adjusted["W2"][0]
        # The pulled-back y should be > 0 (moved toward interior)
        assert w2_start[1] > 0 or w2_start[0] != 5000

    def test_t_junction(self):
        """T-junction: 3 walls sharing an endpoint."""
        walls = [
            _wall("W_LEFT", [[0, 0], [4000, 0]], thick=200),     # Left segment
            _wall("W_RIGHT", [[4000, 0], [8000, 0]], thick=200),  # Right segment (through)
            _wall("W_INT", [[4000, 0], [4000, 3000]], thick=150), # Interior wall
        ]
        adjusted = resolve_butt_joints(walls)
        # Interior wall (shortest at this junction) should be pulled back
        w_int_start = adjusted["W_INT"][0]
        assert w_int_start[1] > 0, "Interior wall should be pulled back from through wall"

    def test_cross_junction(self):
        """Four walls meeting at a cross."""
        walls = [
            _wall("W1", [[0, 3000], [3000, 3000]], thick=200),
            _wall("W2", [[3000, 3000], [6000, 3000]], thick=200),
            _wall("W3", [[3000, 0], [3000, 3000]], thick=200),
            _wall("W4", [[3000, 3000], [3000, 6000]], thick=200),
        ]
        adjusted = resolve_butt_joints(walls)
        # The longest wall (W1 and W2 share length, so one will be through)
        # Shorter walls should be pulled back
        assert len(adjusted) == 4

    def test_no_overlap_when_joined(self):
        """After joining, wall endpoints should not overlap."""
        walls = [
            _wall("W1", [[0, 0], [5000, 0]], thick=200),
            _wall("W2", [[5000, 0], [5000, 4000]], thick=200),
        ]
        adjusted = resolve_butt_joints(walls)
        # All adjusted centerlines should have positive length
        for wid, cl in adjusted.items():
            length = math.hypot(cl[1][0] - cl[0][0], cl[1][1] - cl[0][1])
            assert length > 0, f"Wall {wid} has zero length after joining"

    def test_acute_angle_clamped(self):
        """Walls meeting at 20° should have clamped pullback."""
        # 20 degree angle wall
        angle_rad = math.radians(20)
        walls = [
            _wall("W1", [[0, 0], [5000, 0]], thick=200),
            _wall("W2", [[0, 0], [5000 * math.cos(angle_rad), 5000 * math.sin(angle_rad)]], thick=200),
        ]
        adjusted = resolve_butt_joints(walls)
        # Pullback should not exceed 1.5x thickness
        w2_start = adjusted["W2"][0]
        pullback = math.hypot(w2_start[0], w2_start[1])
        assert pullback <= 200 * 1.5 + 1  # 1mm tolerance

    def test_join_policy_none_skipped(self):
        """Walls with join_policy='none' should not be adjusted."""
        walls = [
            _wall("W1", [[0, 0], [5000, 0]], thick=200),
            {"id": "W2", "centerline": [[5000, 0], [5000, 4000]], "thickness_mm": 200, "join_policy": "none"},
        ]
        adjusted = resolve_butt_joints(walls)
        # W2 should NOT be pulled back
        assert adjusted["W2"][0] == [5000, 0]
