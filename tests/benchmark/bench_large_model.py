"""tests/benchmark/bench_large_model.py — Phase 3 Scalability Benchmark.

Builds a 10×10 grid of rooms (100 walls, up to 200 openings, 100 slabs),
then benchmarks:
  1. Batch create         — single ops.batch, atomic
  2. Chunked create       — dispatch_in_chunks with chunk_size=25
  3. deep_scan (full)     — no pagination
  4. deep_scan (paged)    — limit=25, iterated
  5. deep_scan (attrs)    — include_attrs=True, first page
  6. attr.set_bulk        — tag all walls in one call
  7. attr.find            — query by structural_role with limit

Usage:
    python tests/benchmark/bench_large_model.py [--host localhost] [--port 9876]

SketchUp must be running with the SAIE plugin loaded.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from typing import Any

from su_mcp_bridge.transport.ws_client import SketchUpWSClient
from su_mcp_bridge.core.apply import dispatch_in_chunks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call(client: SketchUpWSClient, method: str, params: dict | None = None,
          timeout: float | None = None) -> Any:
    return client.send_request(method, params or {}, timeout=timeout)


def _timed(label: str, fn) -> tuple[Any, float]:
    t0 = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - t0
    status = "ERROR" if isinstance(result, dict) and result.get("error") else "OK"
    print(f"  [{status}] {label:<50} {elapsed*1000:>8.1f} ms")
    return result, elapsed


# ---------------------------------------------------------------------------
# Model builders
# ---------------------------------------------------------------------------

GRID = 10          # 10×10 = 100 rooms
ROOM_W = 4000      # mm
ROOM_D = 4000      # mm
WALL_H = 2700      # mm
WALL_T = 200       # mm


def build_wall_ops() -> list[dict]:
    """100 walls on a 10×10 grid — outer walls of each room."""
    ops = []
    for row in range(GRID):
        for col in range(GRID):
            x0 = col * ROOM_W
            y0 = row * ROOM_D
            x1 = x0 + ROOM_W
            y1 = y0 + ROOM_D
            ai_id = f"W_{row}_{col}"
            # South wall of each room
            ops.append({
                "method": "ops.wall.create",
                "params": {
                    "ai_id": ai_id,
                    "centerline": [[x0, y0], [x1, y0]],
                    "thickness_mm": WALL_T,
                    "height_mm": WALL_H,
                },
            })
    return ops


def build_slab_ops() -> list[dict]:
    """100 slabs — one floor per room."""
    ops = []
    for row in range(GRID):
        for col in range(GRID):
            x0 = col * ROOM_W
            y0 = row * ROOM_D
            ops.append({
                "method": "ops.slab.create",
                "params": {
                    "ai_id": f"SLAB_{row}_{col}",
                    "polygon": [
                        [x0, y0], [x0 + ROOM_W, y0],
                        [x0 + ROOM_W, y0 + ROOM_D], [x0, y0 + ROOM_D],
                    ],
                    "thickness_mm": 150,
                    "base_z_mm": 0,
                },
            })
    return ops


def build_bim_ops(wall_ids: list[str]) -> list[dict]:
    """BIM attrs for all walls — one ops.attr.set_bulk call."""
    operations = []
    for ai_id in wall_ids:
        operations += [
            {"ai_id": ai_id, "dict_name": "bim", "key": "structural_role", "value": "load_bearing"},
            {"ai_id": ai_id, "dict_name": "bim", "key": "material_spec",   "value": "masonry_clay"},
            {"ai_id": ai_id, "dict_name": "bim", "key": "ifc_class",       "value": "IfcWall"},
            {"ai_id": ai_id, "dict_name": "bim", "key": "cost_per_unit",   "value": 85.0},
            {"ai_id": ai_id, "dict_name": "bim", "key": "quantity_basis",  "value": "m2"},
        ]
    return operations


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_benchmark(host: str = "localhost", port: int = 9876) -> None:
    print(f"\n{'='*65}")
    print(f"  SAIE Phase 3 — Scalability Benchmark")
    print(f"  Grid: {GRID}×{GRID} rooms | {GRID**2} walls | {GRID**2} slabs")
    print(f"{'='*65}\n")

    client = SketchUpWSClient(host=host, port=port, timeout=30.0)
    client.connect()

    wall_ids = [f"W_{r}_{c}" for r in range(GRID) for c in range(GRID)]
    wall_ops  = build_wall_ops()
    slab_ops  = build_slab_ops()
    all_ops   = wall_ops + slab_ops
    n_all     = len(all_ops)

    # ── 0. Clear ──────────────────────────────────────────────────────────
    print("Setup:")
    _timed("Clear model", lambda: _call(client, "ops.clear_model"))

    # ── 1. Single atomic batch ────────────────────────────────────────────
    print("\nBatch create:")
    _timed("Clear model (pre-test)", lambda: _call(client, "ops.clear_model"))
    timeout_single = SketchUpWSClient.batch_timeout(n_all)
    _timed(
        f"Single ops.batch ({n_all} ops, timeout={timeout_single:.0f}s)",
        lambda: _call(client, "ops.batch",
                      {"ops": all_ops, "mode": "atomic"},
                      timeout=timeout_single),
    )

    # ── 2. Chunked dispatch ───────────────────────────────────────────────
    _timed("Clear model (pre-test)", lambda: _call(client, "ops.clear_model"))
    _timed(
        f"dispatch_in_chunks ({n_all} ops, chunk=25)",
        lambda: dispatch_in_chunks(all_ops, client, chunk_size=25, mode="atomic"),
    )

    # ── 3. deep_scan — full ───────────────────────────────────────────────
    print("\nQuery:")
    result, _ = _timed(
        "deep_scan (full, no pagination)",
        lambda: _call(client, "query.deep_scan", {}),
    )
    if isinstance(result, dict):
        n = result.get("summary", {}).get("total_count", "?")
        print(f"           → {n} entities in model")

    # ── 4. deep_scan — paged ─────────────────────────────────────────────
    PAGE = 25
    n_pages = math.ceil(GRID**2 * 2 / PAGE)
    t_paged_start = time.perf_counter()
    entities_seen = 0
    for page in range(n_pages):
        r = _call(client, "query.deep_scan", {"limit": PAGE, "offset": page * PAGE})
        if isinstance(r, dict):
            entities_seen += len(r.get("entities", []))
            if not r.get("page", {}).get("has_more"):
                break
    t_paged = (time.perf_counter() - t_paged_start) * 1000
    print(f"  [OK]  {'deep_scan paged (limit=25, all pages)':<50} {t_paged:>8.1f} ms  → {entities_seen} entities")

    # ── 5. deep_scan — inline attrs ──────────────────────────────────────
    _timed(
        "deep_scan (limit=25, include_attrs=True)",
        lambda: _call(client, "query.deep_scan", {"limit": 25, "include_attrs": True}),
    )

    # ── 6. attr.set_bulk ─────────────────────────────────────────────────
    print("\nBIM Attributes:")
    bim_ops = build_bim_ops(wall_ids)
    _timed(
        f"attr.set_bulk ({len(bim_ops)} writes, {GRID**2} walls)",
        lambda: _call(client, "ops.attr.set_bulk",
                      {"operations": bim_ops},
                      timeout=SketchUpWSClient.batch_timeout(len(bim_ops))),
    )

    # ── 7. attr.find — with limit ────────────────────────────────────────
    _timed(
        "attr.find (structural_role=load_bearing, limit=50)",
        lambda: _call(client, "query.attr.find", {
            "dict_name": "bim",
            "key": "structural_role",
            "value": "load_bearing",
            "limit": 50,
        }),
    )

    _timed(
        "attr.find (structural_role=load_bearing, no limit)",
        lambda: _call(client, "query.attr.find", {
            "dict_name": "bim",
            "key": "structural_role",
            "value": "load_bearing",
        }),
    )

    client.disconnect()
    print(f"\n{'='*65}")
    print("  Benchmark complete.")
    print(f"{'='*65}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SAIE scalability benchmark")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=9876)
    args = parser.parse_args()
    run_benchmark(host=args.host, port=args.port)
