"""Tests for core/apply.py — the diff-to-ops translator."""

import pytest

from su_mcp_bridge.core import (
    BuildingModel,
    Wall,
    Opening,
    Slab,
    Level,
    ProjectMeta,
    diff_models,
    changeset_to_ops,
)
from su_mcp_bridge.core.apply import index_entities_by_id


def _model(walls=None, openings=None, slabs=None) -> BuildingModel:
    return BuildingModel(
        project=ProjectMeta(name="T", display_units="mm"),
        levels=[
            Level(
                id="GF",
                name="Ground",
                walls=walls or [],
                openings=openings or [],
                slabs=slabs or [],
            )
        ],
    )


def _w(id_, x1=0, y1=0, x2=3000, y2=0, t=150, h=2700) -> Wall:
    return Wall(
        id=id_,
        level_id="GF",
        centerline=[[x1, y1], [x2, y2]],
        thickness_mm=t,
        height_mm=h,
    )


def test_empty_diff_yields_no_ops():
    m = _model(walls=[_w("W1")])
    cs = diff_models(m, m)
    assert cs.is_empty()
    assert changeset_to_ops(cs) == []


def test_create_wall_yields_wall_create_op():
    old = _model()
    new = _model(walls=[_w("W1", t=200, h=3000)])
    ops = changeset_to_ops(diff_models(old, new))
    assert len(ops) == 1
    assert ops[0]["method"] == "ops.wall.create"
    assert ops[0]["params"]["ai_id"] == "W1"
    assert ops[0]["params"]["thickness_mm"] == 200
    assert ops[0]["params"]["height_mm"] == 3000


def test_delete_wall_yields_delete_op():
    old = _model(walls=[_w("W1")])
    new = _model()
    ops = changeset_to_ops(diff_models(old, new))
    assert len(ops) == 1
    assert ops[0]["method"] == "ops.delete"
    assert ops[0]["params"]["ai_id"] == "W1"
    assert ops[0]["params"]["entity_type"] == "Wall"


def test_modify_wall_yields_delete_then_create():
    old = _model(walls=[_w("W1", t=150)])
    new = _model(walls=[_w("W1", t=300)])

    cs = diff_models(old, new)
    new_index = index_entities_by_id(new)
    ops = changeset_to_ops(cs, new_entities_by_id=new_index)

    methods = [o["method"] for o in ops]
    assert methods == ["ops.delete", "ops.wall.create"]
    assert ops[0]["params"]["ai_id"] == "W1"
    assert ops[1]["params"]["thickness_mm"] == 300


def test_phase_order_deletes_first_creates_last():
    """A scene that deletes one wall AND creates another must order
    deletes before creates."""
    old = _model(walls=[_w("OLD")])
    new = _model(walls=[_w("NEW")])
    ops = changeset_to_ops(diff_models(old, new))
    methods = [o["method"] for o in ops]
    # delete first, create second
    assert methods.index("ops.delete") < methods.index("ops.wall.create")


def test_create_opening_yields_opening_cut():
    old = _model(walls=[_w("W1")])
    new = _model(
        walls=[_w("W1")],
        openings=[
            Opening(
                id="DOOR_FRONT",
                wall_id="W1",
                kind="door",
                offset_mm=500,
                width_mm=900,
                height_mm=2100,
            )
        ],
    )
    ops = changeset_to_ops(diff_models(old, new))
    cuts = [o for o in ops if o["method"] == "ops.opening.cut"]
    assert len(cuts) == 1
    p = cuts[0]["params"]
    assert p["wall_id"] == "W1"
    assert p["width_mm"] == 900
    assert p["sill_mm"] == 0


def test_create_slab_yields_slab_create():
    old = _model()
    new = _model(
        slabs=[
            Slab(
                id="SLAB",
                level_id="GF",
                polygon=[[0, 0], [3000, 0], [3000, 1000], [0, 1000]],
                thickness_mm=150,
            )
        ]
    )
    ops = changeset_to_ops(diff_models(old, new))
    assert len(ops) == 1
    assert ops[0]["method"] == "ops.slab.create"
    assert ops[0]["params"]["thickness_mm"] == 150


def test_index_entities_by_id_walks_levels():
    m = _model(
        walls=[_w("W1"), _w("W2")],
        openings=[
            Opening(
                id="OP1", wall_id="W1", kind="window",
                offset_mm=0, width_mm=100, height_mm=100, sill_mm=900
            )
        ],
    )
    idx = index_entities_by_id(m)
    assert "W1" in idx
    assert "W2" in idx
    assert "OP1" in idx
    assert idx["W1"]["thickness_mm"] == 150


def test_modify_without_new_data_emits_delete_only_with_warning():
    """If the caller forgets to pass new_entities_by_id, modify becomes
    a delete-only op (with a warning logged) — better than crashing."""
    old = _model(walls=[_w("W1", t=150)])
    new = _model(walls=[_w("W1", t=300)])
    cs = diff_models(old, new)
    ops = changeset_to_ops(cs)  # no new_entities_by_id
    methods = [o["method"] for o in ops]
    assert "ops.delete" in methods
    # No re-create because we didn't pass the new data.
    assert "ops.wall.create" not in methods
