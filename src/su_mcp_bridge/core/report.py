"""core/report.py — Model report generation.

Generates structured reports from deep scan data in Markdown, CSV, and JSON formats.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .logger import get_logger
from .project import get_active_project

log = get_logger(__name__)


def generate_model_report(
    scan_data: dict[str, Any],
    output_dir: str = "",
    bim_data: dict[str, dict[str, Any]] | None = None,
) -> Path:
    """Generate a structured Markdown report from scan data.

    Args:
        scan_data: Output from query.deep_scan RPC
        output_dir: Directory to save to (defaults to active project reports/)
        bim_data: Optional mapping of {ai_id: {key: value}} from query.attr.find.
                  When provided, a BIM Data section and quantity takeoff table are
                  appended. Pass None to skip (backward-compatible default).

    Returns:
        Path to the generated .md file
    """
    project = get_active_project()
    if not output_dir and project:
        output_dir = str(project.reports_dir)
    elif not output_dir:
        output_dir = "."

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = Path(output_dir) / f"model_report_{ts}.md"

    entities = scan_data.get("entities", [])
    summary = scan_data.get("summary", {})
    definitions = scan_data.get("definitions", [])

    # Merge any bim attrs already embedded in scan entity records (future deep_scan).
    # Explicit bim_data arg wins over embedded data.
    merged_bim: dict[str, dict[str, Any]] = {}
    for e in entities:
        ai_id = e.get("ai_id")
        if ai_id and e.get("bim"):
            merged_bim[ai_id] = e["bim"]
    if bim_data:
        merged_bim.update(bim_data)

    lines: list[str] = []
    lines.append("# Model Report — SAIE")
    lines.append("")
    lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Total Entities**: {summary.get('total_entities', len(entities))}")
    lines.append(f"**Total Faces**: {summary.get('total_faces', 'N/A')}")
    lines.append(f"**Total Edges**: {summary.get('total_edges', 'N/A')}")
    lines.append(f"**Solids**: {summary.get('solids_count', 'N/A')}")
    lines.append(f"**Non-Solids**: {summary.get('non_solids_count', 'N/A')}")
    lines.append("")

    # Entity Inventory
    lines.append("## Entity Inventory")
    lines.append("")
    lines.append("| AI ID | Type | Layer | Material | Solid | Volume |")
    lines.append("|-------|------|-------|----------|-------|--------|")
    for e in entities:
        ai_id = e.get("ai_id", "?")
        etype = e.get("type", "?")
        layer = e.get("layer", "-")
        material = e.get("material", "-")
        solid = "Yes" if e.get("is_solid") else "No"
        volume = f"{e.get('volume_mm3', 0):,.0f}" if e.get("volume_mm3") else "-"
        lines.append(f"| {ai_id} | {etype} | {layer} | {material} | {solid} | {volume} |")
    lines.append("")

    # BIM Data section — only when data is present
    if merged_bim:
        bim_keys = [
            "structural_role",
            "material_spec",
            "fire_rating",
            "ifc_class",
            "cost_per_unit",
            "quantity_basis",
            "load_kpa",
        ]
        # Collect only keys that appear at least once
        present_keys = [k for k in bim_keys if any(k in v for v in merged_bim.values())]

        if present_keys:
            lines.append("## BIM Data")
            lines.append("")
            header = "| AI ID | " + " | ".join(present_keys) + " |"
            sep = "|-------|" + "|".join(["-------"] * len(present_keys)) + "|"
            lines.append(header)
            lines.append(sep)
            for e in entities:
                ai_id = e.get("ai_id", "?")
                bim = merged_bim.get(ai_id, {})
                row = (
                    f"| {ai_id} | " + " | ".join(str(bim.get(k, "—")) for k in present_keys) + " |"
                )
                lines.append(row)
            lines.append("")

        # Quantity Takeoff — entities that have both cost_per_unit and quantity_basis
        takeoff_rows = []
        for e in entities:
            ai_id = e.get("ai_id", "?")
            bim = merged_bim.get(ai_id, {})
            cost = bim.get("cost_per_unit")
            basis = bim.get("quantity_basis")
            if cost is None or basis is None:
                continue
            vol_mm3 = e.get("volume_mm3", 0) or 0
            # Derive quantity from geometry and basis unit
            if basis == "m3":
                qty = vol_mm3 / 1e9
            elif basis == "m2":
                qty = (vol_mm3 / 1e9) ** (2 / 3)  # rough; real area comes from scan
            elif basis == "lm":
                qty = (vol_mm3 / 1e9) ** (1 / 3)
            else:
                qty = 1.0  # nr / kg / tonne — count
            total = round(qty * float(cost), 2)
            takeoff_rows.append((ai_id, e.get("type", "?"), basis, round(qty, 3), cost, total))

        if takeoff_rows:
            lines.append("## Quantity Takeoff")
            lines.append("")
            lines.append("| AI ID | Type | Unit | Qty | Rate | Total |")
            lines.append("|-------|------|------|-----|------|-------|")
            grand_total = 0.0
            for ai_id, etype, basis, qty, rate, total in takeoff_rows:
                lines.append(f"| {ai_id} | {etype} | {basis} | {qty} | {rate} | {total} |")
                grand_total += total
            lines.append(f"| **TOTAL** | | | | | **{round(grand_total, 2)}** |")
            lines.append("")

    # Material Usage
    mat_usage: dict[str, int] = {}
    for e in entities:
        mat = e.get("material", "None")
        mat_usage[mat] = mat_usage.get(mat, 0) + 1
    if mat_usage:
        lines.append("## Material Usage")
        lines.append("")
        lines.append("| Material | Count |")
        lines.append("|----------|-------|")
        for mat, count in sorted(mat_usage.items()):
            lines.append(f"| {mat} | {count} |")
        lines.append("")

    # Layer Summary
    layer_usage: dict[str, int] = {}
    for e in entities:
        layer = e.get("layer", "Default")
        layer_usage[layer] = layer_usage.get(layer, 0) + 1
    if layer_usage:
        lines.append("## Layer Summary")
        lines.append("")
        lines.append("| Layer | Entities |")
        lines.append("|-------|----------|")
        for layer, count in sorted(layer_usage.items()):
            lines.append(f"| {layer} | {count} |")
        lines.append("")

    # Definitions
    if definitions:
        lines.append("## Component Definitions")
        lines.append("")
        lines.append("| Name | Instances | Faces | Edges | Solid |")
        lines.append("|------|-----------|-------|-------|-------|")
        for d in definitions:
            solid = "Yes" if d.get("is_solid") else "No"
            lines.append(
                f"| {d.get('name', '?')} | {d.get('instances_count', 0)} | {d.get('faces', 0)} | {d.get('edges', 0)} | {solid} |"
            )
        lines.append("")

    # Warnings
    warnings = [e for e in entities if not e.get("is_solid") or not e.get("ai_id")]
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in warnings:
            if not w.get("is_solid"):
                lines.append(
                    f"- **{w.get('ai_id', '?')}** ({w.get('type', '?')}): Non-solid geometry"
                )
            if not w.get("ai_id"):
                lines.append(f"- Entity with GUID {w.get('guid', '?')}: Missing ai_id")
        lines.append("")

    content = "\n".join(lines)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    log.info(f"Model report generated: {filepath}")
    return filepath


def generate_csv_inventory(
    scan_data: dict[str, Any],
    output_dir: str = "",
    bim_data: dict[str, dict[str, Any]] | None = None,
) -> Path:
    """Generate a CSV inventory from scan data, with optional BIM attribute columns.

    Args:
        scan_data: Output from query.deep_scan RPC
        output_dir: Directory to save to (defaults to active project reports/)
        bim_data: Optional {ai_id: {key: value}} mapping — adds BIM columns to CSV
    """
    project = get_active_project()
    if not output_dir and project:
        output_dir = str(project.reports_dir)
    elif not output_dir:
        output_dir = "."

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = Path(output_dir) / f"inventory_{ts}.csv"

    entities = scan_data.get("entities", [])

    merged_bim: dict[str, dict[str, Any]] = {}
    for e in entities:
        ai_id = e.get("ai_id")
        if ai_id and e.get("bim"):
            merged_bim[ai_id] = e["bim"]
    if bim_data:
        merged_bim.update(bim_data)

    bim_keys = [
        "structural_role",
        "material_spec",
        "fire_rating",
        "ifc_class",
        "cost_per_unit",
        "quantity_basis",
        "load_kpa",
        "notes",
    ]

    base_cols = [
        "ai_id",
        "type",
        "layer",
        "material",
        "is_solid",
        "face_count",
        "edge_count",
        "volume_mm3",
        "min_x",
        "min_y",
        "min_z",
        "max_x",
        "max_y",
        "max_z",
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(base_cols + (bim_keys if merged_bim else []))
        for e in entities:
            bounds = e.get("bounds_mm", {})
            mins = bounds.get("min", [0, 0, 0])
            maxs = bounds.get("max", [0, 0, 0])
            ai_id = e.get("ai_id", "")
            bim = merged_bim.get(ai_id, {}) if merged_bim else {}
            row = [
                ai_id,
                e.get("type", ""),
                e.get("layer", ""),
                e.get("material", ""),
                e.get("is_solid", False),
                e.get("face_count", 0),
                e.get("edge_count", 0),
                e.get("volume_mm3", 0),
                mins[0] if len(mins) > 0 else 0,
                mins[1] if len(mins) > 1 else 0,
                mins[2] if len(mins) > 2 else 0,
                maxs[0] if len(maxs) > 0 else 0,
                maxs[1] if len(maxs) > 1 else 0,
                maxs[2] if len(maxs) > 2 else 0,
            ]
            if merged_bim:
                row += [bim.get(k, "") for k in bim_keys]
            writer.writerow(row)

    log.info(f"CSV inventory generated: {filepath}")
    return filepath


def generate_json_snapshot(scan_data: dict[str, Any], output_dir: str = "") -> Path:
    """Save raw scan data as a JSON snapshot."""
    project = get_active_project()
    if not output_dir and project:
        output_dir = str(project.data_dir)
    elif not output_dir:
        output_dir = "."

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = Path(output_dir) / f"model_snapshot_{ts}.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(scan_data, f, indent=2, ensure_ascii=False)

    log.info(f"JSON snapshot saved: {filepath}")
    return filepath
