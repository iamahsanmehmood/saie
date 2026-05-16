# Changelog — SketchUp Automation & Intelligence Engine (SAIE)

All notable changes to this project will be documented in this file.

> Project formerly known as "SU MCP Bridge". The Python package and CLI binary retain their original names (`su_mcp_bridge` / `sb`) for backward compatibility.

## [1.0.0] - Unreleased

### Added — Phase 3: Scalability Optimization
- **`deep_scan` pagination**: `limit`, `offset`, `type_filter` params added. Response includes a `"page"` envelope (`offset`, `limit`, `returned`, `total`, `has_more`). Safe for models with 500+ entities.
- **`deep_scan` inline attrs**: `include_attrs: true` embeds all attribute dictionaries on each entity record under `"attrs"` — eliminates N+1 `query.attr.get` calls.
- **`query.attr.find` limits**: `limit` (early exit after N matches) and `depth` (cap recursion depth) params added to prevent runaway scans on complex nested models.
- **Adaptive timeout** (`SketchUpWSClient.batch_timeout(n_ops)`): Scales WebSocket timeout linearly with batch size (`15s + 0.8s/op`, capped at 300s). Auto-applied to all `ops.batch` calls in `server.py`.
- **`dispatch_in_chunks()`** (`core/apply.py`): Splits large op lists into sequential atomic chunks (default 50 ops each). Preserves partial progress — committed chunks survive a later chunk failure.
- **Benchmark suite** (`tests/benchmark/bench_large_model.py`): Builds a 10×10 room grid and measures 7 scenarios — single batch, chunked dispatch, full/paged/inline-attr scans, `attr.set_bulk`, and `attr.find` with/without limit.
- **MCP tools updated**: `deep_scan` and `find_entities_by_attribute` now expose all new params to AI agents.

### Added — Phase 2: Data Integration
- **BIM Attribute DB**: Five new JSON-RPC ops — `query.attr.get`, `query.attr.list`, `query.attr.find`, `ops.attr.set`, `ops.attr.set_bulk`. See `ruby_plugin/su_mcp_bridge/ops/attr.rb`.
- **BIM Metadata Schema** (`docs/bim_metadata_schema.md`): Standard `"bim"` dictionary with `structural_role`, `material_spec`, `fire_rating`, `thermal_resistance`, `ifc_class`, `cost_per_unit`, `quantity_basis`, `load_kpa`, `notes`.
- **Five new MCP tools**: `get_entity_attribute`, `list_entity_dictionaries`, `find_entities_by_attribute`, `set_entity_attribute`, `set_entity_attributes_bulk`.
- **Enhanced reports**: `generate_model_report()` and `generate_csv_inventory()` accept optional `bim_data` arg — adds BIM Data table and Quantity Takeoff section with grand total.

### Added — Phase 1: Core Framework (initial release)

### Added — Core Pipeline
- **Ruby JSON-RPC Server**: Persistent WebSocket server running natively inside SketchUp 2025 (`ws://localhost:9876`). Handles walls, openings, slabs, roofs, primitives, components, materials, layers, captures, lifecycle, and animation ops.
- **Intelligent Wall Joining Protocol**: Python-side geometry calculation (`resolve_butt_joints`) pre-emptively shrinks and pulls back intersecting centerlines for pristine butt/T/cross junctions without z-fighting.
- **Upsert on Create**: All `create` ops (wall, slab, roof, primitive) safely replace an existing entity when a named `ai_id` is provided — safe for AI retry loops and batch replays.
- **Batch Mode (`atomic` | `best_effort`)**: `ops.batch` now supports two isolation modes. `"atomic"` (default) wraps all ops in one undo step and aborts on any failure. `"best_effort"` runs each op independently and returns inline error entries for failed ops.
- **WebP Capture System**: Pillow intercepts `.png` capture requests and transcodes to `.webp`, reducing payload latency for visual LLM agents.
- **DXF Floorplan Parser**: `ezdxf` pipeline extracts 2D lines/polylines and converts them to an `ops.batch` model for zero-shot 3D floorplan building.
- **Local LLM Agent Integration**: `OllamaAgent` drives SketchUp via offline models (Qwen 2.5, Llama 3, Gemma) using OpenAI-compatible tool structures.
- **`sb` CLI**: 20+ commands for full terminal control of the bridge.
- **MCP Server (40+ tools)**: Compatible with Claude Desktop, Claude Code, and Antigravity.

### Added — Data Integration (Phase 2)
- **BIM Attribute DB** (`query.attr.*` / `ops.attr.*`): Five new ops expose SketchUp's attribute dictionary surface — get, list, find (with predicate), set, and atomic bulk set.
- **BIM Metadata Schema**: Standard `"bim"` dictionary with keys `structural_role`, `material_spec`, `fire_rating`, `thermal_resistance`, `ifc_class`, `cost_per_unit`, `quantity_basis`, `load_kpa`, `notes`. See `docs/bim_metadata_schema.md`.
- **Enhanced Reports**: `generate_model_report()` and `generate_csv_inventory()` include BIM Data and Quantity Takeoff sections when `bim_data` is supplied.

### Added — Documentation
- `docs/action_schema.md`: Full action format specification — wire format, conventions, catalog of all ops, compliance checklist.
- `docs/bim_metadata_schema.md`: BIM attribute dictionary reference with usage examples.

### Fixed
- Boolean state tracking: `query.verify` now recursively deep-traverses geometry to recover `ai_id` after SketchUp destroys parent walls during boolean door/window subtractions.
- Batch point extrusion: fixed "Duplicate points in array" crash from malformed array params.
- CLI `--preset` argument parsing in `sb capture`.
- Bounds output now in mm throughout (was leaking SketchUp-native inches).

### Infrastructure
- Migrated legacy TCP sockets to persistent `websockets` with auto-reconnect and synchronous ID-correlation.
- `PROTOCOL_VERSION = '1.0'`, `PLUGIN_VERSION = '1.0.0'`.
