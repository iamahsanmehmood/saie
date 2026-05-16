"""core/units.py — Unit conversion helpers.

The internal data model is in millimetres. The wire protocol to SketchUp uses
inches (SketchUp's native unit). This module is the single, audited place
that conversion happens. Do NOT scatter `/ 25.4` literals across the codebase.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

# Exact conversion factor (international inch).
MM_PER_INCH: float = 25.4
"""Exact conversion factor: 1 inch == 25.4 mm by definition (international inch)."""

# Tolerance for "is this a degenerate / zero" comparison, in mm.
EPS_MM: float = 1.0


def mm_to_in(value: float) -> float:
    """Convert millimetres to inches."""
    return float(value) / MM_PER_INCH


def in_to_mm(value: float) -> float:
    """Convert inches to millimetres."""
    return float(value) * MM_PER_INCH


def point_mm_to_in(point: Sequence[float]) -> List[float]:
    """Convert an N-D point in mm to a list in inches.

    Works for 2-D and 3-D. Preserves the dimensionality.
    """
    return [mm_to_in(c) for c in point]


def point_in_to_mm(point: Sequence[float]) -> List[float]:
    """Convert an N-D point in inches to a list in mm."""
    return [in_to_mm(c) for c in point]


def polygon_mm_to_in(polygon: Iterable[Sequence[float]]) -> List[List[float]]:
    """Convert a polygon (list of points) from mm to inches."""
    return [point_mm_to_in(p) for p in polygon]


def polygon_in_to_mm(polygon: Iterable[Sequence[float]]) -> List[List[float]]:
    """Convert a polygon (list of points) from inches to mm."""
    return [point_in_to_mm(p) for p in polygon]


def round_mm(value: float, ndigits: int = 3) -> float:
    """Round a millimetre value. Default 0.001mm = 1um precision is plenty."""
    return round(float(value), ndigits)


def feet_inches_to_mm(feet: float, inches: float = 0.0) -> float:
    """Convenience: feet+inches -> mm. Useful for plan markup."""
    return in_to_mm(feet * 12.0 + inches)


def mm_to_feet_inches(value_mm: float) -> Tuple[int, float]:
    """Return (feet, remaining_inches). Inches kept as float for precision."""
    total_inches = mm_to_in(value_mm)
    feet = int(total_inches // 12)
    inches = total_inches - feet * 12
    return feet, inches
