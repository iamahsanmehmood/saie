"""core/clash.py — Python-side clash analysis with rule-based checks.

Complements the Ruby AABB clash detection with higher-level rules
that analyze the building model semantically.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .geometry import wall_length_mm, points_coincident_mm
from .logger import get_logger
from .project import get_active_project

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


# ---------------------------------------------------------------------------
# Clash result
# ---------------------------------------------------------------------------

class ClashResult:
    """A single clash finding."""
    def __init__(self, entity_a: str, entity_b: str, rule: str,
                 severity: str, message: str):
        self.entity_a = entity_a
        self.entity_b = entity_b
        self.rule = rule
        self.severity = severity
        self.message = message

    def to_dict(self) -> dict:
        return {
            "entity_a": self.entity_a,
            "entity_b": self.entity_b,
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
        }


class ClashReport:
    """Collection of clash results with summary."""
    def __init__(self):
        self.findings: List[ClashResult] = []

    def add(self, finding: ClashResult):
        self.findings.append(finding)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_INFO)

    @property
    def is_clean(self) -> bool:
        return self.error_count == 0 and self.warning_count == 0

    def to_dict(self) -> dict:
        return {
            "total": len(self.findings),
            "errors": self.error_count,
            "warnings": self.warning_count,
            "info": self.info_count,
            "status": "clean" if self.is_clean else "clashes_found",
            "findings": [f.to_dict() for f in self.findings],
        }


# ---------------------------------------------------------------------------
# Rule checks
# ---------------------------------------------------------------------------

def _check_wall_wall_overlap(entities: List[Dict]) -> List[ClashResult]:
    """Rule: Two walls with overlapping bounding boxes (not at joints)."""
    results = []
    walls = [e for e in entities if e.get("type") == "wall"]

    for i, w1 in enumerate(walls):
        bb1 = w1.get("bounds_mm", {})
        min1 = bb1.get("min", [0, 0, 0])
        max1 = bb1.get("max", [0, 0, 0])

        for w2 in walls[i + 1:]:
            bb2 = w2.get("bounds_mm", {})
            min2 = bb2.get("min", [0, 0, 0])
            max2 = bb2.get("max", [0, 0, 0])

            # Check 3-axis AABB overlap
            if (min1[0] < max2[0] and max1[0] > min2[0] and
                min1[1] < max2[1] and max1[1] > min2[1] and
                min1[2] < max2[2] and max1[2] > min2[2]):

                # Calculate overlap volume
                dx = max(0, min(max1[0], max2[0]) - max(min1[0], min2[0]))
                dy = max(0, min(max1[1], max2[1]) - max(min1[1], min2[1]))
                dz = max(0, min(max1[2], max2[2]) - max(min1[2], min2[2]))
                vol = dx * dy * dz

                if vol > 1000:  # > 1cm³
                    results.append(ClashResult(
                        w1.get("ai_id", "?"), w2.get("ai_id", "?"),
                        "wall_wall_overlap",
                        SEVERITY_ERROR,
                        f"Wall-wall overlap: {vol:.0f} mm³"
                    ))
    return results


def _check_opening_bounds(entities: List[Dict]) -> List[ClashResult]:
    """Rule: Opening exceeds wall bounds."""
    results = []
    walls = {e["ai_id"]: e for e in entities if e.get("type") == "wall" and e.get("ai_id")}

    for wall_id, wall in walls.items():
        spec = wall.get("spec")
        openings = wall.get("openings", [])
        if not spec or not openings:
            continue

        centerline = spec.get("centerline")
        height_mm = spec.get("height_mm", 2800)
        if not centerline:
            continue

        try:
            wlen = wall_length_mm(centerline)
        except Exception:
            continue

        for op in openings:
            offset = op.get("offset_mm", 0)
            width = op.get("width_mm", 900)
            sill = op.get("sill_mm", 0)
            op_height = op.get("height_mm", 2100)
            op_id = op.get("ai_id", "?")

            if offset + width > wlen + 1:  # 1mm tolerance
                results.append(ClashResult(
                    op_id, wall_id,
                    "opening_exceeds_wall_length",
                    SEVERITY_ERROR,
                    f"Opening extends past wall: offset({offset}) + width({width}) = {offset + width:.0f} > wall length {wlen:.0f}"
                ))

            if sill + op_height > height_mm + 1:
                results.append(ClashResult(
                    op_id, wall_id,
                    "opening_exceeds_wall_height",
                    SEVERITY_ERROR,
                    f"Opening exceeds wall height: sill({sill}) + height({op_height}) = {sill + op_height} > {height_mm}"
                ))
    return results


def _check_slab_wall_z_overlap(entities: List[Dict]) -> List[ClashResult]:
    """Rule: Slab and wall z-axis overlap (slab should sit below walls, not through them)."""
    results = []
    walls = [e for e in entities if e.get("type") == "wall"]
    slabs = [e for e in entities if e.get("type") == "slab"]

    for slab in slabs:
        sbb = slab.get("bounds_mm", {})
        s_min_z = sbb.get("min", [0, 0, 0])[2] if len(sbb.get("min", [])) > 2 else 0
        s_max_z = sbb.get("max", [0, 0, 0])[2] if len(sbb.get("max", [])) > 2 else 0
        slab_thick = s_max_z - s_min_z

        for wall in walls:
            wbb = wall.get("bounds_mm", {})
            w_min_z = wbb.get("min", [0, 0, 0])[2] if len(wbb.get("min", [])) > 2 else 0
            w_max_z = wbb.get("max", [0, 0, 0])[2] if len(wbb.get("max", [])) > 2 else 0

            # Slab significantly overlaps wall vertically (not just touching)
            overlap_z = min(s_max_z, w_max_z) - max(s_min_z, w_min_z)
            if overlap_z > slab_thick * 0.5 and overlap_z > 50:  # > 50mm
                results.append(ClashResult(
                    slab.get("ai_id", "?"), wall.get("ai_id", "?"),
                    "slab_wall_z_overlap",
                    SEVERITY_WARNING,
                    f"Slab-wall Z overlap: {overlap_z:.0f}mm"
                ))
    return results


def _check_component_collision(entities: List[Dict]) -> List[ClashResult]:
    """Rule: Component-component AABB collision."""
    results = []
    components = [e for e in entities if e.get("type") in ("component", "primitive")]

    for i, c1 in enumerate(components):
        bb1 = c1.get("bounds_mm", {})
        min1 = bb1.get("min", [0, 0, 0])
        max1 = bb1.get("max", [0, 0, 0])

        for c2 in components[i + 1:]:
            bb2 = c2.get("bounds_mm", {})
            min2 = bb2.get("min", [0, 0, 0])
            max2 = bb2.get("max", [0, 0, 0])

            if (min1[0] < max2[0] and max1[0] > min2[0] and
                min1[1] < max2[1] and max1[1] > min2[1] and
                min1[2] < max2[2] and max1[2] > min2[2]):
                results.append(ClashResult(
                    c1.get("ai_id", "?"), c2.get("ai_id", "?"),
                    "component_collision",
                    SEVERITY_WARNING,
                    "Component bounding boxes overlap"
                ))
    return results


# ---------------------------------------------------------------------------
# Main analyzer
# ---------------------------------------------------------------------------

def analyze_clashes(scan_data: Dict[str, Any]) -> ClashReport:
    """Run all clash rules against deep scan data.
    
    Args:
        scan_data: Output from query.deep_scan
    
    Returns:
        ClashReport with all findings
    """
    report = ClashReport()
    entities = scan_data.get("entities", [])

    for check in [
        _check_wall_wall_overlap,
        _check_opening_bounds,
        _check_slab_wall_z_overlap,
        _check_component_collision,
    ]:
        for finding in check(entities):
            report.add(finding)

    log.info(f"Clash analysis: {len(report.findings)} findings "
             f"({report.error_count} errors, {report.warning_count} warnings)")
    return report


def generate_clash_report_md(report: ClashReport, output_dir: str = "") -> Path:
    """Generate a Markdown clash report."""
    project = get_active_project()
    if not output_dir and project:
        output_dir = str(project.reports_dir)
    elif not output_dir:
        output_dir = "."

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = Path(output_dir) / f"clash_report_{ts}.md"

    lines = [
        "# Clash Detection Report",
        "",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Status**: {'✅ Clean' if report.is_clean else '❌ Clashes Found'}",
        f"**Errors**: {report.error_count}",
        f"**Warnings**: {report.warning_count}",
        f"**Info**: {report.info_count}",
        "",
    ]

    if report.findings:
        lines.append("## Findings")
        lines.append("")
        lines.append("| Severity | Entity A | Entity B | Rule | Message |")
        lines.append("|----------|----------|----------|------|---------|")
        for f in report.findings:
            sev_icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(f.severity, "⚪")
            lines.append(f"| {sev_icon} {f.severity} | {f.entity_a} | {f.entity_b} | {f.rule} | {f.message} |")
        lines.append("")
    else:
        lines.append("No clashes detected. Model geometry is clean.")
        lines.append("")

    content = "\n".join(lines)
    with open(filepath, "w", encoding="utf-8") as fp:
        fp.write(content)

    log.info(f"Clash report saved: {filepath}")
    return filepath


def generate_clash_report_json(report: ClashReport, output_dir: str = "") -> Path:
    """Save clash report as JSON."""
    project = get_active_project()
    if not output_dir and project:
        output_dir = str(project.data_dir)
    elif not output_dir:
        output_dir = "."

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = Path(output_dir) / f"clash_data_{ts}.json"

    with open(filepath, "w", encoding="utf-8") as fp:
        json.dump(report.to_dict(), fp, indent=2)

    log.info(f"Clash JSON saved: {filepath}")
    return filepath
