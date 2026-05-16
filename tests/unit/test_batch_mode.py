"""tests/unit/test_batch_mode.py — Unit tests for batch mode, adaptive timeout,
and chunked dispatch logic (pure Python, no SketchUp connection required).
"""

from __future__ import annotations

import math
import pytest
from unittest.mock import MagicMock, call, patch

from su_mcp_bridge.transport.ws_client import SketchUpWSClient
from su_mcp_bridge.core.apply import dispatch_in_chunks, changeset_to_ops
from su_mcp_bridge.core.diff import ChangeSet, EntityCreated


# ---------------------------------------------------------------------------
# SketchUpWSClient.batch_timeout
# ---------------------------------------------------------------------------

class TestBatchTimeout:
    def test_zero_ops_returns_base(self):
        t = SketchUpWSClient.batch_timeout(0)
        assert t == SketchUpWSClient._BATCH_BASE_S

    def test_scales_linearly(self):
        t10  = SketchUpWSClient.batch_timeout(10)
        t20  = SketchUpWSClient.batch_timeout(20)
        delta = SketchUpWSClient._BATCH_PER_OP_S * 10
        assert abs((t20 - t10) - delta) < 0.001

    def test_capped_at_max(self):
        t = SketchUpWSClient.batch_timeout(10_000)
        assert t == SketchUpWSClient._BATCH_MAX_S

    def test_typical_50_ops(self):
        t = SketchUpWSClient.batch_timeout(50)
        expected = min(
            SketchUpWSClient._BATCH_BASE_S + 50 * SketchUpWSClient._BATCH_PER_OP_S,
            SketchUpWSClient._BATCH_MAX_S,
        )
        assert abs(t - expected) < 0.001

    def test_always_positive(self):
        assert SketchUpWSClient.batch_timeout(0) > 0
        assert SketchUpWSClient.batch_timeout(1) > 0


# ---------------------------------------------------------------------------
# dispatch_in_chunks
# ---------------------------------------------------------------------------

def _make_ops(n: int) -> list[dict]:
    return [{"method": f"ops.wall.create", "params": {"ai_id": f"W{i}"}} for i in range(n)]


def _mock_client(results_per_call=None):
    """Return a mock client whose send_request returns successive result lists."""
    client = MagicMock()
    if results_per_call is not None:
        client.send_request.side_effect = results_per_call
    else:
        client.send_request.return_value = [{"status": "created"}]
    return client


class TestDispatchInChunks:
    def test_empty_ops_returns_empty(self):
        client = _mock_client()
        result = dispatch_in_chunks([], client)
        assert result == []
        client.send_request.assert_not_called()

    def test_single_chunk_when_ops_lte_chunk_size(self):
        ops = _make_ops(10)
        client = _mock_client([[{"status": "created"}] * 10])
        results = dispatch_in_chunks(ops, client, chunk_size=50)
        assert client.send_request.call_count == 1
        sent_params = client.send_request.call_args[0][1]
        assert len(sent_params["ops"]) == 10

    def test_correct_number_of_chunks(self):
        ops = _make_ops(100)
        chunk_size = 25
        n_chunks = math.ceil(100 / chunk_size)
        client = _mock_client([[{"s": "ok"}] * chunk_size] * n_chunks)
        dispatch_in_chunks(ops, client, chunk_size=chunk_size)
        assert client.send_request.call_count == n_chunks

    def test_chunks_cover_all_ops(self):
        ops = _make_ops(55)
        chunk_size = 20
        sent_ops = []
        def capture(*args, **kwargs):
            sent_ops.extend(args[1]["ops"])
            return [{"s": "ok"}]
        client = MagicMock()
        client.send_request.side_effect = capture
        dispatch_in_chunks(ops, client, chunk_size=chunk_size)
        assert len(sent_ops) == 55

    def test_results_flattened_in_order(self):
        ops = _make_ops(6)
        chunk_size = 3
        client = _mock_client([
            [{"ai_id": "W0"}, {"ai_id": "W1"}, {"ai_id": "W2"}],
            [{"ai_id": "W3"}, {"ai_id": "W4"}, {"ai_id": "W5"}],
        ])
        results = dispatch_in_chunks(ops, client, chunk_size=chunk_size)
        assert [r["ai_id"] for r in results] == ["W0", "W1", "W2", "W3", "W4", "W5"]

    def test_raises_on_error_result(self):
        ops = _make_ops(10)
        client = _mock_client([{"error": "Wall not found: W0"}])
        with pytest.raises(RuntimeError, match="Chunk 1/1 failed"):
            dispatch_in_chunks(ops, client, chunk_size=50)

    def test_mode_forwarded_to_bridge(self):
        ops = _make_ops(5)
        client = _mock_client([[{"s": "ok"}] * 5])
        dispatch_in_chunks(ops, client, chunk_size=50, mode="best_effort")
        sent_params = client.send_request.call_args[0][1]
        assert sent_params["mode"] == "best_effort"

    def test_adaptive_timeout_used(self):
        ops = _make_ops(30)
        timeouts_used = []
        def capture(method, params, timeout=None):
            timeouts_used.append(timeout)
            return [{"s": "ok"}] * len(params["ops"])
        client = MagicMock()
        client.send_request.side_effect = capture
        dispatch_in_chunks(ops, client, chunk_size=30)
        assert len(timeouts_used) == 1
        expected = SketchUpWSClient.batch_timeout(30)
        assert abs(timeouts_used[0] - expected) < 0.001


# ---------------------------------------------------------------------------
# changeset_to_ops — ordering invariants
# ---------------------------------------------------------------------------

class TestChangesetToOps:
    def _make_changeset(self, created_types: list[str]) -> ChangeSet:
        created = [
            EntityCreated(
                entity_id=f"{t}_{i}",
                entity_type=t,
                data={"id": f"{t}_{i}", "centerline": [[0,0],[1000,0]],
                      "thickness_mm": 200, "height_mm": 2700} if t == "Wall"
                     else {"id": f"{t}_{i}"},
            )
            for i, t in enumerate(created_types)
        ]
        return ChangeSet(created=created, deleted=[], modified=[])

    def test_material_before_wall(self):
        cs = self._make_changeset(["Wall", "Material"])
        ops = changeset_to_ops(cs)
        methods = [o["method"] for o in ops]
        mat_idx  = next(i for i, m in enumerate(methods) if "material" in m)
        wall_idx = next(i for i, m in enumerate(methods) if "wall" in m)
        assert mat_idx < wall_idx

    def test_wall_before_opening(self):
        created = [
            EntityCreated(
                entity_id="D1", entity_type="Opening",
                data={"id": "D1", "wall_id": "W1", "offset_mm": 500,
                      "width_mm": 900, "height_mm": 2100},
            ),
            EntityCreated(
                entity_id="W1", entity_type="Wall",
                data={"id": "W1", "centerline": [[0,0],[6000,0]],
                      "thickness_mm": 200, "height_mm": 2700},
            ),
        ]
        cs = ChangeSet(created=created, deleted=[], modified=[])
        ops = changeset_to_ops(cs)
        methods = [o["method"] for o in ops]
        wall_idx    = next(i for i, m in enumerate(methods) if "wall.create" in m)
        opening_idx = next(i for i, m in enumerate(methods) if "opening" in m)
        assert wall_idx < opening_idx

    def test_deletes_before_creates(self):
        from su_mcp_bridge.core.diff import EntityDeleted
        cs = ChangeSet(
            created=[EntityCreated(entity_id="W_new", entity_type="Wall",
                                   data={"id": "W_new", "centerline": [[0,0],[1000,0]],
                                         "thickness_mm": 200, "height_mm": 2700})],
            deleted=[EntityDeleted(entity_id="W_old", entity_type="Wall")],
            modified=[],
        )
        ops = changeset_to_ops(cs)
        methods = [o["method"] for o in ops]
        delete_idx = next(i for i, m in enumerate(methods) if "delete" in m)
        create_idx = next(i for i, m in enumerate(methods) if "create" in m)
        assert delete_idx < create_idx
