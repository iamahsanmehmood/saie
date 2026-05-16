"""tests/unit/test_report_bim.py — Unit tests for BIM-enhanced report generation.

Tests the bim_data integration in generate_model_report and
generate_csv_inventory without touching the filesystem (uses tmp_path fixture).
"""

from __future__ import annotations

import csv
import pytest

from su_mcp_bridge.core.report import generate_model_report, generate_csv_inventory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _scan_data(n: int = 3) -> dict:
    entities = []
    for i in range(n):
        entities.append({
            "ai_id":      f"W{i}",
            "type":       "wall",
            "layer":      "GF",
            "material":   "BRICK",
            "is_solid":   True,
            "volume_mm3": 1_000_000.0 * (i + 1),
            "face_count": 6,
            "edge_count": 12,
            "bounds_mm":  {"min": [0, 0, 0], "max": [1000, 200, 2700]},
        })
    return {
        "entities":    entities,
        "definitions": [],
        "summary": {
            "total_entities": n,
            "total_faces":    n * 6,
            "total_edges":    n * 12,
            "solids_count":   n,
            "non_solids_count": 0,
        },
    }


def _bim_data() -> dict:
    return {
        "W0": {"structural_role": "load_bearing", "material_spec": "masonry_clay",
               "fire_rating": "60min", "ifc_class": "IfcWall",
               "cost_per_unit": 85.0, "quantity_basis": "m2"},
        "W1": {"structural_role": "partition",    "cost_per_unit": 40.0,
               "quantity_basis": "m2"},
        "W2": {"structural_role": "load_bearing", "fire_rating": "90min"},
    }


# ---------------------------------------------------------------------------
# generate_model_report
# ---------------------------------------------------------------------------

class TestGenerateModelReport:
    def test_creates_md_file(self, tmp_path):
        path = generate_model_report(_scan_data(), output_dir=str(tmp_path))
        assert path.exists()
        assert path.suffix == ".md"

    def test_contains_entity_ids(self, tmp_path):
        path = generate_model_report(_scan_data(), output_dir=str(tmp_path))
        content = path.read_text(encoding="utf-8")
        assert "W0" in content
        assert "W1" in content
        assert "W2" in content

    def test_no_bim_section_without_data(self, tmp_path):
        path = generate_model_report(_scan_data(), output_dir=str(tmp_path))
        content = path.read_text(encoding="utf-8")
        assert "## BIM Data" not in content

    def test_bim_section_present_with_data(self, tmp_path):
        path = generate_model_report(
            _scan_data(), output_dir=str(tmp_path), bim_data=_bim_data()
        )
        content = path.read_text(encoding="utf-8")
        assert "## BIM Data" in content

    def test_bim_section_contains_known_keys(self, tmp_path):
        path = generate_model_report(
            _scan_data(), output_dir=str(tmp_path), bim_data=_bim_data()
        )
        content = path.read_text(encoding="utf-8")
        assert "structural_role" in content
        assert "load_bearing" in content
        assert "60min" in content

    def test_quantity_takeoff_section_present(self, tmp_path):
        path = generate_model_report(
            _scan_data(), output_dir=str(tmp_path), bim_data=_bim_data()
        )
        content = path.read_text(encoding="utf-8")
        assert "## Quantity Takeoff" in content
        assert "TOTAL" in content

    def test_backward_compat_no_bim_arg(self, tmp_path):
        path = generate_model_report(_scan_data(), output_dir=str(tmp_path))
        content = path.read_text(encoding="utf-8")
        assert "## Entity Inventory" in content

    def test_saie_header(self, tmp_path):
        path = generate_model_report(_scan_data(), output_dir=str(tmp_path))
        content = path.read_text(encoding="utf-8")
        assert "SAIE" in content

    def test_embedded_bim_in_scan_used(self, tmp_path):
        scan = _scan_data(1)
        scan["entities"][0]["bim"] = {"structural_role": "shear_wall"}
        path = generate_model_report(scan, output_dir=str(tmp_path))
        content = path.read_text(encoding="utf-8")
        assert "## BIM Data" in content
        assert "shear_wall" in content

    def test_explicit_bim_data_wins_over_embedded(self, tmp_path):
        scan = _scan_data(1)
        scan["entities"][0]["bim"] = {"structural_role": "partition"}
        explicit = {"W0": {"structural_role": "load_bearing"}}
        path = generate_model_report(scan, output_dir=str(tmp_path), bim_data=explicit)
        content = path.read_text(encoding="utf-8")
        assert "load_bearing" in content


# ---------------------------------------------------------------------------
# generate_csv_inventory
# ---------------------------------------------------------------------------

class TestGenerateCsvInventory:
    def test_creates_csv_file(self, tmp_path):
        path = generate_csv_inventory(_scan_data(), output_dir=str(tmp_path))
        assert path.exists()
        assert path.suffix == ".csv"

    def test_base_columns_present(self, tmp_path):
        path = generate_csv_inventory(_scan_data(), output_dir=str(tmp_path))
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert "ai_id" in reader.fieldnames
            assert "type" in reader.fieldnames
            assert "volume_mm3" in reader.fieldnames

    def test_no_bim_columns_without_data(self, tmp_path):
        path = generate_csv_inventory(_scan_data(), output_dir=str(tmp_path))
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert "structural_role" not in reader.fieldnames

    def test_bim_columns_present_with_data(self, tmp_path):
        path = generate_csv_inventory(
            _scan_data(), output_dir=str(tmp_path), bim_data=_bim_data()
        )
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert "structural_role" in reader.fieldnames
            assert "ifc_class" in reader.fieldnames

    def test_bim_values_in_rows(self, tmp_path):
        path = generate_csv_inventory(
            _scan_data(), output_dir=str(tmp_path), bim_data=_bim_data()
        )
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        w0 = next(r for r in rows if r["ai_id"] == "W0")
        assert w0["structural_role"] == "load_bearing"
        assert w0["fire_rating"] == "60min"

    def test_missing_bim_entity_shows_empty(self, tmp_path):
        bim = {"W0": {"structural_role": "load_bearing"}}
        path = generate_csv_inventory(
            _scan_data(2), output_dir=str(tmp_path), bim_data=bim
        )
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        w1 = next(r for r in rows if r["ai_id"] == "W1")
        assert w1["structural_role"] == ""

    def test_row_count_matches_entities(self, tmp_path):
        path = generate_csv_inventory(_scan_data(5), output_dir=str(tmp_path))
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 5
