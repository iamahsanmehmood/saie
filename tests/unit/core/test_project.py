"""Tests for core/project.py — project folder lifecycle."""

import json
from pathlib import Path

import pytest

from su_mcp_bridge.core import (
    BuildingModel,
    Wall,
    Level,
    ProjectMeta,
)
from su_mcp_bridge.core.project import Project, ProjectLockError, empty_model


def _model() -> BuildingModel:
    return BuildingModel(
        project=ProjectMeta(name="TestProject", display_units="mm"),
        levels=[
            Level(
                id="GF",
                name="GF",
                walls=[
                    Wall(id="W1", level_id="GF", centerline=[[0, 0], [3000, 0]],
                         thickness_mm=150, height_mm=2700),
                ],
            )
        ],
    )


def test_create_scaffolds_required_dirs(tmp_path: Path):
    p = Project.create(tmp_path / "demo", _model())
    try:
        for d in ["snapshots", "history", "history/building_versions",
                  "captures/views", "captures/ad_hoc", "exports", "logs"]:
            assert (tmp_path / "demo" / d).is_dir(), f"missing {d}"
        assert (tmp_path / "demo" / "building.json").exists()
        assert (tmp_path / "demo" / "project.json").exists()
    finally:
        p.close()


def test_create_then_open_round_trip(tmp_path: Path):
    Project.create(tmp_path / "house", _model()).close()
    with Project.open(tmp_path / "house") as p:
        m = p.load_model()
        assert m.project.name == "TestProject"
        assert m.levels[0].walls[0].id == "W1"


def test_lock_prevents_concurrent_open(tmp_path: Path):
    Project.create(tmp_path / "house", _model()).close()
    p1 = Project.open(tmp_path / "house")
    try:
        with pytest.raises(ProjectLockError):
            Project.open(tmp_path / "house")  # already locked by p1
    finally:
        p1.close()


def test_save_model_writes_manifest_with_hash(tmp_path: Path):
    p = Project.create(tmp_path / "h", _model())
    try:
        m = p.load_model()
        m.levels[0].walls.append(
            Wall(id="W2", level_id="GF", centerline=[[0, 0], [0, 1000]],
                 thickness_mm=150, height_mm=2700)
        )
        h = p.save_model(m)
        assert isinstance(h, str) and len(h) == 40  # sha1 hex
        manifest = json.loads((tmp_path / "h" / "project.json").read_text())
        assert manifest["model_hash"] == h
        assert manifest["name"] == "TestProject"
    finally:
        p.close()


def test_auto_versioning_on_save(tmp_path: Path):
    p = Project.create(tmp_path / "h", _model())
    try:
        m = p.load_model()
        # The initial save does NOT create a version (it's the seed); subsequent ones do.
        for i in range(3):
            m.metadata.notes = f"edit {i}"
            p.save_model(m)
        versions = list((tmp_path / "h" / "history" / "building_versions").glob("building.*.json"))
        assert len(versions) >= 3
    finally:
        p.close()


def test_save_snapshot_named_immutable_copy(tmp_path: Path):
    p = Project.create(tmp_path / "h", _model())
    try:
        target = p.save_snapshot("v0.1-walls")
        assert target.exists()
        names = p.list_snapshots()
        assert any("v0.1-walls" in n for n in names)
    finally:
        p.close()


def test_restore_snapshot(tmp_path: Path):
    p = Project.create(tmp_path / "h", _model())
    try:
        snapshot_path = p.save_snapshot("baseline")
        m = p.load_model()
        m.levels[0].walls = []
        p.save_model(m)

        restored = p.restore_snapshot(snapshot_path.name)
        assert len(restored.levels[0].walls) == 1
    finally:
        p.close()


def test_memory_append_and_read(tmp_path: Path):
    p = Project.create(tmp_path / "h", _model())
    try:
        p.append_memory("First note")
        p.append_memory("Second note")
        contents = p.read_memory()
        assert "First note" in contents
        assert "Second note" in contents
    finally:
        p.close()


def test_empty_model_helper():
    m = empty_model("Hello")
    assert m.project.name == "Hello"
    assert m.levels == []
