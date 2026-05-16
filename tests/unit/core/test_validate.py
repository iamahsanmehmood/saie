"""Tests for core/validate.py — semantic validation rules."""

import pytest

from su_mcp_bridge.core import (
    BuildingModel,
    Wall,
    Opening,
    Slab,
    Material,
    Level,
    ProjectMeta,
    validate_model,
)


def _wall(id_="W1", x1=0, y1=0, x2=3000, y2=0, t=150, h=2700) -> Wall:
    return Wall(id=id_, level_id="GF", centerline=[[x1, y1], [x2, y2]],
                thickness_mm=t, height_mm=h)


def _model(walls=None, openings=None, slabs=None, materials=None) -> BuildingModel:
    return BuildingModel(
        project=ProjectMeta(name="T"),
        materials=materials or [],
        levels=[
            Level(id="GF", name="GF",
                  walls=walls or [], openings=openings or [], slabs=slabs or [])
        ],
    )


def test_clean_model_no_issues():
    m = _model(walls=[_wall("W1")])
    assert validate_model(m) == []


def test_zero_length_wall_flagged():
    m = _model(walls=[_wall("W1", x1=0, y1=0, x2=0, y2=0)])
    issues = validate_model(m)
    msgs = " ".join(i.message for i in issues)
    assert "less than 1mm" in msgs


def test_opening_overflow_offset_plus_width():
    m = _model(
        walls=[_wall("W1", x1=0, y1=0, x2=1000, y2=0)],  # 1m long
        openings=[Opening(
            id="DOOR", wall_id="W1", kind="door",
            offset_mm=900, width_mm=500, height_mm=2100,  # 900+500=1400 > 1000
        )],
    )
    issues = validate_model(m)
    assert any("exceeds wall length" in i.message for i in issues)


def test_opening_overflow_sill_plus_height():
    m = _model(
        walls=[_wall("W1", h=2700)],
        openings=[Opening(
            id="W", wall_id="W1", kind="window",
            offset_mm=0, width_mm=500, height_mm=2000, sill_mm=1000,  # 3000 > 2700
        )],
    )
    issues = validate_model(m)
    assert any("exceeds wall height" in i.message for i in issues)


def test_dangling_wall_id_in_opening():
    m = _model(
        walls=[_wall("W1")],
        openings=[Opening(
            id="DOOR", wall_id="DOES_NOT_EXIST", kind="door",
            offset_mm=0, width_mm=500, height_mm=2000,
        )],
    )
    issues = validate_model(m)
    assert any("non-existent wall_id" in i.message for i in issues)


def test_invalid_material_id_in_wall():
    m = _model(
        walls=[Wall(
            id="W1", level_id="GF",
            centerline=[[0, 0], [3000, 0]],
            thickness_mm=150, height_mm=2700,
            material_id_exterior="BOGUS",
        )],
        materials=[Material(id="REAL", name="Real")],
    )
    issues = validate_model(m)
    assert any("Invalid material_id_exterior: BOGUS" in i.message for i in issues)


def test_slab_with_two_points_flagged():
    m = _model(slabs=[Slab(id="S", level_id="GF", polygon=[[0, 0], [1000, 0]], thickness_mm=150)])
    issues = validate_model(m)
    assert any("at least 3 points" in i.message for i in issues)


def test_negative_offset_flagged():
    m = _model(
        walls=[_wall("W1")],
        openings=[Opening(
            id="X", wall_id="W1", kind="door",
            offset_mm=-100, width_mm=500, height_mm=2000,
        )],
    )
    issues = validate_model(m)
    assert any("offset cannot be negative" in i.message for i in issues)
