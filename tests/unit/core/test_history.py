from pathlib import Path

import pytest

from su_mcp_bridge.core.history import History, OpRecord


def test_append_and_iter(tmp_path: Path):
    h = History(tmp_path / "history" / "operations.jsonl")
    h.append(OpRecord.new("WallCreated", entity_id="W1", payload={"t": 150}))
    h.append(OpRecord.new("WallCreated", entity_id="W2", payload={"t": 200}))

    records = list(h.iter_records())
    assert len(records) == 2
    assert records[0].entity_id == "W1"
    assert records[1].entity_id == "W2"
    assert records[0].kind == "WallCreated"


def test_count_returns_zero_when_no_log(tmp_path: Path):
    h = History(tmp_path / "history" / "operations.jsonl")
    assert h.count() == 0


def test_count_after_appends(tmp_path: Path):
    h = History(tmp_path / "history" / "operations.jsonl")
    for i in range(5):
        h.append(OpRecord.new("OpeningCut", entity_id=f"OP_{i}"))
    assert h.count() == 5


def test_list_recent_returns_newest_first(tmp_path: Path):
    h = History(tmp_path / "history" / "operations.jsonl")
    for i in range(10):
        h.append(OpRecord.new("X", entity_id=f"E_{i}"))

    recent = h.list_recent(limit=3)
    ids = [r.entity_id for r in recent]
    assert ids == ["E_9", "E_8", "E_7"]


def test_clear_wipes_log(tmp_path: Path):
    h = History(tmp_path / "history" / "operations.jsonl")
    h.append(OpRecord.new("X"))
    assert h.count() == 1
    h.clear()
    assert h.count() == 0


def test_op_record_inverse_round_trip(tmp_path: Path):
    h = History(tmp_path / "h.jsonl")
    forward = {"method": "ops.wall.create", "params": {"ai_id": "W1"}}
    inverse = {"method": "ops.delete", "params": {"ai_id": "W1"}}
    h.append(OpRecord.new("WallCreated", entity_id="W1", payload=forward, inverse=inverse))

    records = list(h.iter_records())
    assert records[0].payload == forward
    assert records[0].inverse == inverse


def test_malformed_lines_are_skipped(tmp_path: Path):
    p = tmp_path / "h.jsonl"
    p.write_text("not-json\n" + '{"op_id":"x","ts":1.0,"kind":"X"}\n', encoding="utf-8")
    h = History(p)
    records = list(h.iter_records())
    assert len(records) == 1
    assert records[0].op_id == "x"
