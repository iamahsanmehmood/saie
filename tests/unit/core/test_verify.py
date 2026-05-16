"""Tests for core/verify.py — post-apply state divergence detection."""

import pytest

from su_mcp_bridge.core import (
    BuildingModel,
    Wall,
    Opening,
    Level,
    ProjectMeta,
)
from su_mcp_bridge.core.verify import verify, expected_entity_ids


def _model_with_two_walls() -> BuildingModel:
    return BuildingModel(
        project=ProjectMeta(name="T"),
        levels=[
            Level(
                id="GF",
                name="Ground",
                walls=[
                    Wall(
                        id="W1",
                        level_id="GF",
                        centerline=[[0, 0], [3000, 0]],
                        thickness_mm=150,
                        height_mm=2700,
                    ),
                    Wall(
                        id="W2",
                        level_id="GF",
                        centerline=[[3000, 0], [3000, 4000]],
                        thickness_mm=150,
                        height_mm=2700,
                    ),
                ],
                openings=[
                    Opening(
                        id="DOOR",
                        wall_id="W1",
                        kind="door",
                        offset_mm=500,
                        width_mm=900,
                        height_mm=2100,
                    )
                ],
            )
        ],
    )


def test_expected_entity_ids_includes_walls_openings():
    m = _model_with_two_walls()
    ids = expected_entity_ids(m)
    assert ids == {"W1", "W2", "DOOR"}


def test_verify_clean_match():
    m = _model_with_two_walls()
    sk_export = {
        "entities": [
            {"ai_id": "W1", "guid": "g1", "valid_solid": True},
            {"ai_id": "W2", "guid": "g2", "valid_solid": True},
            {"ai_id": "DOOR", "guid": "g3", "valid_solid": True},
        ],
        "total": 3,
    }
    report = verify(m, sk_export)
    assert report.ok
    assert report.divergences == []
    assert report.missing == set()
    assert report.orphans == set()


def test_verify_detects_missing_entity():
    m = _model_with_two_walls()
    sk_export = {
        "entities": [
            {"ai_id": "W1", "guid": "g1", "valid_solid": True},
            # W2 missing
            {"ai_id": "DOOR", "guid": "g3", "valid_solid": True},
        ]
    }
    report = verify(m, sk_export)
    assert not report.ok
    assert "W2" in report.missing
    assert any(d.code == "MISSING" and d.entity_id == "W2" for d in report.divergences)


def test_verify_warns_on_orphan_entity():
    m = _model_with_two_walls()
    sk_export = {
        "entities": [
            {"ai_id": "W1", "guid": "g1", "valid_solid": True},
            {"ai_id": "W2", "guid": "g2", "valid_solid": True},
            {"ai_id": "DOOR", "guid": "g3", "valid_solid": True},
            {"ai_id": "GHOST", "guid": "x", "valid_solid": True},
        ]
    }
    report = verify(m, sk_export)
    # Orphans are warnings, not errors -> overall ok is True.
    assert report.ok
    assert "GHOST" in report.orphans
    assert any(d.code == "ORPHAN" and d.severity == "warning" for d in report.divergences)


def test_verify_warns_on_non_manifold_solid():
    m = _model_with_two_walls()
    sk_export = {
        "entities": [
            {"ai_id": "W1", "guid": "g1", "valid_solid": True},
            {"ai_id": "W2", "guid": "g2", "valid_solid": False},  # broken!
            {"ai_id": "DOOR", "guid": "g3", "valid_solid": True},
        ]
    }
    report = verify(m, sk_export)
    assert any(d.code == "NON_MANIFOLD" and d.entity_id == "W2" for d in report.divergences)


def test_verify_handles_empty_export():
    m = _model_with_two_walls()
    report = verify(m, {"entities": [], "total": 0})
    assert not report.ok
    assert report.missing == {"W1", "W2", "DOOR"}
