"""core/geometry.py — Pure geometry helpers (mm).

The Python "truth" for wall lengths, polygon areas, miter angles, etc.
The Ruby plugin has parallel implementations in `ruby_plugin/su_mcp_bridge/ops/`,
kept in test parity with these.

All inputs/outputs are in millimetres unless explicitly suffixed `_in`.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple, Dict, Any

from .units import EPS_MM


Point2D = Sequence[float]  # [x, y]
Point3D = Sequence[float]  # [x, y, z]


# ---------------------------------------------------------------------------
# Wall and segment helpers
# ---------------------------------------------------------------------------


def wall_length_mm(centerline: Sequence[Sequence[float]]) -> float:
    """Length of a 2-point wall centerline in mm.

    Raises ValueError if the centerline is malformed.
    """
    if len(centerline) != 2:
        raise ValueError(f"centerline must have exactly 2 points, got {len(centerline)}")
    (x1, y1), (x2, y2) = centerline[0], centerline[1]
    dx = float(x2) - float(x1)
    dy = float(y2) - float(y1)
    return math.hypot(dx, dy)


def wall_unit_vector(centerline: Sequence[Sequence[float]]) -> Tuple[float, float]:
    """Unit vector along the wall centerline (start -> end)."""
    length = wall_length_mm(centerline)
    if length < EPS_MM:
        raise ValueError("Cannot compute unit vector for zero-length wall")
    (x1, y1), (x2, y2) = centerline[0], centerline[1]
    return ((x2 - x1) / length, (y2 - y1) / length)


def wall_perpendicular(centerline: Sequence[Sequence[float]]) -> Tuple[float, float]:
    """Unit perpendicular to the wall centerline (left-handed: rotate +90 CCW).

    Returned vector is the "exterior" direction in plan if the centerline
    is traced clockwise around a building footprint.
    """
    ux, uy = wall_unit_vector(centerline)
    return (-uy, ux)


def wall_axis_aligned(
    centerline: Sequence[Sequence[float]], tolerance_deg: float = 1.0
) -> str:
    """Classify the wall direction.

    Returns one of:
      - "x"  : axis-aligned along world X (within tolerance_deg)
      - "y"  : axis-aligned along world Y
      - "diag" : diagonal (NOT axis-aligned)

    The v1 prototype used `dy > dx` from the bounding box which fails on
    diagonal walls. v2 uses the actual centerline direction.
    """
    ux, uy = wall_unit_vector(centerline)
    angle_deg = math.degrees(math.atan2(abs(uy), abs(ux)))
    # 0deg = pure X, 90deg = pure Y
    if angle_deg <= tolerance_deg:
        return "x"
    if angle_deg >= 90.0 - tolerance_deg:
        return "y"
    return "diag"


def miter_angle_deg(
    centerline_a: Sequence[Sequence[float]], centerline_b: Sequence[Sequence[float]]
) -> float:
    """Interior angle (degrees) between two walls meeting at a shared endpoint.

    Returns the angle in [0, 180]. 90 = clean L-corner. 180 = collinear.
    Caller is expected to have verified that the walls share an endpoint.
    """
    ax, ay = wall_unit_vector(centerline_a)
    bx, by = wall_unit_vector(centerline_b)
    dot = max(-1.0, min(1.0, ax * bx + ay * by))
    return math.degrees(math.acos(dot))


# ---------------------------------------------------------------------------
# Polygon helpers (slabs, roofs, footprints)
# ---------------------------------------------------------------------------


def polygon_area_mm(polygon: Sequence[Sequence[float]]) -> float:
    """Signed shoelace area in mm^2. Positive = CCW, negative = CW."""
    if len(polygon) < 3:
        return 0.0
    total = 0.0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i][0], polygon[i][1]
        x2, y2 = polygon[(i + 1) % n][0], polygon[(i + 1) % n][1]
        total += (x1 * y2) - (x2 * y1)
    return total / 2.0


def polygon_is_ccw(polygon: Sequence[Sequence[float]]) -> bool:
    """True iff polygon vertices wind counter-clockwise."""
    return polygon_area_mm(polygon) > 0.0


def polygon_centroid_mm(polygon: Sequence[Sequence[float]]) -> Tuple[float, float]:
    """Geometric centroid (NOT vertex-mean) of a simple polygon."""
    if len(polygon) < 3:
        raise ValueError("polygon needs at least 3 points")
    area = polygon_area_mm(polygon)
    if abs(area) < EPS_MM * EPS_MM:
        # degenerate -- fall back to vertex mean
        cx = sum(p[0] for p in polygon) / len(polygon)
        cy = sum(p[1] for p in polygon) / len(polygon)
        return (cx, cy)
    cx = cy = 0.0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i][0], polygon[i][1]
        x2, y2 = polygon[(i + 1) % n][0], polygon[(i + 1) % n][1]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    factor = 1.0 / (6.0 * area)
    return (cx * factor, cy * factor)


def point_in_polygon_mm(point: Point2D, polygon: Sequence[Sequence[float]]) -> bool:
    """Even-odd rule. True if point is strictly inside polygon."""
    x, y = point[0], point[1]
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]
        intersect = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


def _segments_intersect(
    a: Point2D, b: Point2D, c: Point2D, d: Point2D
) -> bool:
    """Return True iff segment AB and segment CD properly intersect.

    Endpoint-coincident cases return False (we want STRICT crossing).
    """
    def ccw(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    d1 = ccw(c, d, a)
    d2 = ccw(c, d, b)
    d3 = ccw(a, b, c)
    d4 = ccw(a, b, d)

    if (
        ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0))
        and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0))
    ):
        return True
    return False


def polygon_is_simple(polygon: Sequence[Sequence[float]]) -> bool:
    """True iff polygon has no self-intersections (excluding shared vertices)."""
    n = len(polygon)
    if n < 4:
        return True  # triangles can't self-intersect
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        for j in range(i + 1, n):
            # Skip adjacent edges (they share a vertex)
            if abs(i - j) <= 1 or (i == 0 and j == n - 1):
                continue
            c, d = polygon[j], polygon[(j + 1) % n]
            if _segments_intersect(a, b, c, d):
                return False
    return True


def points_coincident_mm(
    p1: Point2D, p2: Point2D, tolerance_mm: float = EPS_MM
) -> bool:
    """True if two points coincide within tolerance (default 1mm)."""
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    return math.hypot(dx, dy) <= tolerance_mm


def bounding_box_mm(
    polygon: Sequence[Sequence[float]],
) -> Tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) of a polygon. Empty -> all zeros."""
    if not polygon:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return (min(xs), min(ys), max(xs), max(ys))


def classify_junction(members: list, walls: list) -> str:
    """Classify a junction where multiple wall endpoints meet.
    
    Returns one of: "end", "L", "T", "cross"
    """
    if len(members) <= 1:
        return "end"
    
    # Count how many walls have this point at start vs end
    wall_ids = set(m[1] for m in members)
    n_walls = len(wall_ids)
    
    if n_walls == 2:
        # Two walls meeting: check if one passes through
        for m in members:
            wid = m[1]
            idx = m[2]
            w = next(w for w in walls if w["id"] == wid)
            cl = w["centerline"]
            other_pt = cl[1 - idx]
            # If the junction point is NOT at either end of the wall,
            # it's a T-junction (but since we only track endpoints, 
            # 2-wall junctions are always L-corners)
            pass
        return "L"
    elif n_walls == 3:
        return "T"
    elif n_walls >= 4:
        return "cross"
    return "L"


def _find_through_wall(members: list, walls: list):
    """For T/cross junctions, find the wall that passes through.
    
    The through wall is the longest wall. For T-junctions, it's the wall
    whose centerline the other wall(s) terminate against.
    """
    wall_objs = []
    seen = set()
    for m in members:
        wid = m[1]
        if wid not in seen:
            seen.add(wid)
            wall_objs.append(next(w for w in walls if w["id"] == wid))
    wall_objs.sort(key=lambda w: wall_length_mm(w["centerline"]), reverse=True)
    return wall_objs[0], wall_objs[1:]


def validate_wall_network(walls: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Pre-flight check for impossible or problematic wall geometry.
    
    Returns a list of warning dicts: {"wall_id": ..., "warning": ...}
    """
    warnings = []
    for w in walls:
        cl = w["centerline"]
        length = wall_length_mm(cl)
        thick = w.get("thickness_mm", 150)
        
        if length < EPS_MM:
            warnings.append({"wall_id": w["id"], "warning": "Zero-length wall"})
        elif length < thick:
            warnings.append({"wall_id": w["id"], "warning": f"Wall length ({length:.0f}mm) shorter than thickness ({thick:.0f}mm)"})
        
        height = w.get("height_mm", 2800)
        if height <= 0:
            warnings.append({"wall_id": w["id"], "warning": "Non-positive wall height"})
    
    # Check for duplicate/overlapping walls
    for i, w1 in enumerate(walls):
        for w2 in walls[i+1:]:
            cl1, cl2 = w1["centerline"], w2["centerline"]
            if (points_coincident_mm(cl1[0], cl2[0]) and points_coincident_mm(cl1[1], cl2[1])) or \
               (points_coincident_mm(cl1[0], cl2[1]) and points_coincident_mm(cl1[1], cl2[0])):
                warnings.append({"wall_id": w1["id"], "warning": f"Overlaps with {w2['id']}"})
    
    return warnings


def resolve_butt_joints(walls: List[Dict[str, Any]]) -> Dict[str, List[List[float]]]:
    """Resolve wall junctions to prevent overlapping geometry.
    
    Given a list of wall dictionaries (with 'id', 'centerline', 'thickness_mm'),
    finds all shared endpoints and pulls back the abutting (shorter) walls by
    half the thickness of the through (longest) wall.
    
    Handles L-corners, T-junctions, and cross-junctions.
    
    Returns a dictionary mapping wall 'id' to its newly adjusted centerline.
    """
    adjusted = {w["id"]: [list(w["centerline"][0]), list(w["centerline"][1])] for w in walls}
    
    # Extract all endpoints
    endpoints = []
    for w in walls:
        endpoints.append((w["centerline"][0], w["id"], 0))  # 0 = start
        endpoints.append((w["centerline"][1], w["id"], 1))  # 1 = end
        
    # Group coincident endpoints
    groups = []
    for ep in endpoints:
        pt = ep[0]
        found = False
        for g in groups:
            if points_coincident_mm(g["pt"], pt):
                g["members"].append(ep)
                found = True
                break
        if not found:
            groups.append({"pt": pt, "members": [ep]})
            
    # Process each junction
    for g in groups:
        members = g["members"]
        if len(members) < 2:
            continue
        
        junction_type = classify_junction(members, walls)
        
        # Find the through wall (longest) and abutting walls
        through_wall, abutting_walls = _find_through_wall(members, walls)
        through_thick = through_wall["thickness_mm"]
        
        # Pull back each abutting wall
        for m in members:
            wid = m[1]
            if wid == through_wall["id"]:
                continue
                
            idx = m[2]
            other_idx = 1 - idx
            
            w = next(w for w in walls if w["id"] == wid)
            if w.get("join_policy", "auto") == "none":
                continue
                
            P = w["centerline"][idx]
            other_P = w["centerline"][other_idx]
            
            dx = other_P[0] - P[0]
            dy = other_P[1] - P[1]
            length = math.hypot(dx, dy)
            if length < EPS_MM:
                continue
            ux, uy = dx / length, dy / length
            
            # Calculate angle between abutting wall and through wall
            tw_P0 = through_wall["centerline"][0]
            tw_P1 = through_wall["centerline"][1]
            tw_dx = tw_P1[0] - tw_P0[0]
            tw_dy = tw_P1[1] - tw_P0[1]
            tw_len = math.hypot(tw_dx, tw_dy)
            if tw_len < EPS_MM:
                continue
            tw_ux, tw_uy = tw_dx / tw_len, tw_dy / tw_len
            
            dot = max(-1.0, min(1.0, ux * tw_ux + uy * tw_uy))
            theta = math.acos(dot)
            sin_theta = math.sin(theta)
            
            # Acute angle clamping: for angles < 30°, cap pullback
            if abs(sin_theta) < 0.17:  # < ~10 degrees (nearly parallel)
                pullback = through_thick / 2.0
            elif abs(sin_theta) < 0.5:  # < 30 degrees (acute)
                # Clamp to prevent extreme pullback
                pullback = min(through_thick / 2.0 / abs(sin_theta), through_thick * 1.5)
            else:
                pullback = (through_thick / 2.0) / abs(sin_theta)
            
            # Never pull back more than 90% of the wall length
            pullback = min(pullback, length * 0.9)
            
            new_P = [P[0] + ux * pullback, P[1] + uy * pullback]
            adjusted[wid][idx] = new_P
            
    return adjusted
