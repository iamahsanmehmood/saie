# SAIE Action Schema (v3.0)

**Status:** Phase 1 — Core Framework. This document is the canonical contract for every action that flows through the SAIE pipeline. New ops MUST conform; existing ops are documented as-implemented and discrepancies are called out.

The "action format" is the unit of work that flows: `AI / CLI → Python → WebSocket JSON-RPC → Ruby plugin → SketchUp`. Standardizing it is what makes batching, undo, replay, and headless cloud execution tractable.

---

## 1. Wire format — JSON-RPC 2.0

Every action is a JSON-RPC 2.0 request over the persistent WebSocket (`ws://localhost:9876`).

### 1.1 Request envelope

```json
{
  "jsonrpc": "2.0",
  "id": "<unique correlation id, string or int>",
  "method": "<dotted method name, e.g. ops.wall.create>",
  "params": { "...": "..." }
}
```

| Field     | Type   | Required | Notes |
|-----------|--------|----------|-------|
| `jsonrpc` | string | yes      | Must be `"2.0"`. |
| `id`      | string\|int | yes | Caller-chosen; the response echoes it. The Python client uses it for synchronous correlation. |
| `method`  | string | yes      | Dotted identifier from §3 (the Action Catalog). |
| `params`  | object | yes      | May be `{}`. Never `null`. |

### 1.2 Success response

```json
{
  "jsonrpc": "2.0",
  "id": "<echo>",
  "result": { "...handler return hash..." }
}
```

The `result` is the handler's return hash verbatim. **Domain errors are carried inside `result`**, not in the JSON-RPC `error` envelope (see §1.4). This keeps the call site simple: clients always read `result["error"]` to detect domain failures.

### 1.3 Protocol-level error response

Reserved for parse failures, unknown methods, and unhandled Ruby exceptions:

```json
{
  "jsonrpc": "2.0",
  "id": "<echo or null>",
  "error": {
    "code": -32601,
    "message": "Method not found: ops.foo.bar",
    "data": { "exception": "...", "backtrace": "..." }
  }
}
```

Code map (from [ruby_plugin/su_mcp_bridge/envelope.rb](../ruby_plugin/su_mcp_bridge/envelope.rb)):

| Code     | Constant            | Meaning |
|----------|---------------------|---------|
| `-32700` | `PARSE_ERROR`       | JSON parse failure. |
| `-32600` | `INVALID_REQUEST`   | Malformed JSON-RPC envelope. |
| `-32601` | `METHOD_NOT_FOUND`  | No handler registered for `method`. |
| `-32602` | `INVALID_PARAMS`    | Schema violation in `params`. |
| `-32603` | `INTERNAL_ERROR`    | Unhandled Ruby exception. |
| `-32000` | `APP_ERROR`         | Generic domain error (reserved). |
| `-32001` | `NOT_FOUND`         | Entity by `ai_id` missing. |
| `-32002` | `VALIDATION`        | Invalid geometry / params. |
| `-32003` | `BOOLEAN_FAILED`    | Boolean subtract returned nil. |
| `-32004` | `BUSY`              | Model is in another `start_operation`. |

### 1.4 Domain error (carried inside `result`)

```json
{
  "jsonrpc": "2.0",
  "id": "<echo>",
  "result": { "error": "Wall not found: W1" }
}
```

Handlers that detect a recoverable domain failure return `{ "error": "<message>" }`. Clients must check `result["error"]` before consuming other fields.

---

## 2. Common parameter conventions

These conventions are normative for every new op.

### 2.1 Units

- **All linear dimensions in `params` are millimeters.** Field names carry the unit suffix: `width_mm`, `height_mm`, `thickness_mm`, `base_z_mm`, `ridge_height_mm`, `eave_overhang_mm`.
- **All angles are degrees.** Field names carry the suffix: `pitch_deg`, `rotation_deg`.
- **Coordinates are 2D `[x, y]` (mm) for footprints / centerlines, 3D `[x, y, z]` (mm) for transforms.** Never mix.

The Ruby layer converts mm → SketchUp inches at the boundary (`MM_TO_IN = 1.0 / 25.4`). Python and the AI never see inches.

### 2.2 Identifiers (`ai_id`)

Every persistent entity gets a stable string `ai_id`. This is the AI's primary key and survives boolean operations.

- Provide `params["ai_id"]` (preferred) or `params["id"]` (back-compat alias).
- If omitted on a `create`, the Ruby layer auto-names via `AI_ID.auto_name(:wall, [x, y])` and returns the generated id in `result["ai_id"]`.
- **`ai_id` is required for every `modify` and `delete` op.** Returns a domain error if missing.
- Stored on the SketchUp group via `set_attribute("su_mcp_bridge", "ai_id", ...)` so it persists across save/reopen.

### 2.3 Tagging

`params["tags"]` is an optional array of strings (`["exterior", "load_bearing"]`) attached to the entity for downstream filtering and reporting. Default `[]`.

### 2.4 Layers / levels

`params["level"]` (default `"GF"`) routes the entity to a SketchUp layer (Tag). Use for floor-level grouping (`"GF"`, `"L1"`, `"L2"`, `"Roof"`).

### 2.5 Standard `result` shape (create ops)

```json
{
  "ai_id": "W1",
  "guid":  "<sketchup native guid>",
  "status": "created | upserted",
  "bounds": { "min": [x_mm, y_mm, z_mm], "max": [x_mm, y_mm, z_mm] }
}
```

`bounds` is in **mm** (3 decimal places). `status` is `"created"` for new entities, `"upserted"` when a named `ai_id` already existed and was replaced.

### 2.6 Standard `result` shape (modify / delete ops)

```json
{ "ai_id": "W1", "status": "deleted" }
{ "ai_id": "W1", "status": "modified" }
```

---

## 3. Action Catalog (Phase 1)

Methods are grouped by domain. Each entry: `method`, required params, optional params, result shape, error modes.

### 3.1 System

| Method | Purpose |
|--------|---------|
| `ping` | Liveness check. Returns `{ pong: true, time, plugin_version }`. |
| `hello` | Handshake. Returns `{ protocol_version, plugin_version, capabilities: [...method names...] }`. |

### 3.2 Walls — `ops.wall.*`

#### `ops.wall.create`

```json
{
  "method": "ops.wall.create",
  "params": {
    "ai_id": "W1",
    "centerline": [[0, 0], [6000, 0]],
    "thickness_mm": 200,
    "height_mm": 2700,
    "base_z_mm": 0,
    "level": "GF",
    "tags": ["exterior"]
  }
}
```

| Param          | Type           | Required | Default | Notes |
|----------------|----------------|----------|---------|-------|
| `ai_id`        | string         | no       | auto    | Stable id; auto-generated if omitted. |
| `centerline`   | `[[x,y],[x,y]]` | yes (v2) | —       | mm. v1 alias: `start_x/start_y/end_x/end_y` (inches, deprecated). |
| `thickness_mm` | number         | no       | 200     | mm. |
| `height_mm`    | number         | no       | 2700    | mm. |
| `base_z_mm`    | number         | no       | 0       | mm. |
| `level`        | string         | no       | `"GF"`  | Layer/Tag name. |
| `tags`         | string[]       | no       | `[]`    | |

**Errors:** `"zero-length wall"` (centerline length < 0.001 inch).

#### `ops.wall.modify`
Required: `ai_id` + same body as `create`. Implementation: erases + recreates (boolean op invariant). Caller is responsible for re-cutting any openings on the rebuilt wall.

#### `ops.wall.delete`
Required: `ai_id`. Returns `{ ai_id, status: "deleted" }`. Errors: `"Wall not found: <ai_id>"`.

### 3.3 Openings — `ops.opening.*`

#### `ops.opening.cut`

```json
{
  "method": "ops.opening.cut",
  "params": {
    "ai_id": "DOOR_1",
    "wall_id": "W1",
    "kind": "door",
    "offset_mm": 1500,
    "width_mm": 900,
    "height_mm": 2100,
    "sill_mm": 0,
    "tags": []
  }
}
```

| Param        | Type   | Required | Notes |
|--------------|--------|----------|-------|
| `ai_id`      | string | no       | auto-generated if omitted. |
| `wall_id`    | string | **yes**  | The host wall's `ai_id`. |
| `kind`       | string | no       | `"door"` \| `"window"` (informational; geometry is identical). |
| `offset_mm`  | number | yes      | Distance along wall centerline from start. |
| `width_mm`   | number | yes      | |
| `height_mm`  | number | yes      | |
| `sill_mm`    | number | no (0)   | Distance from wall base to opening bottom. Use 0 for doors. |

**Errors:** `"wall_id is required"`, `"Wall not found: <wall_id>"`, `"Could not determine wall frame for <wall_id>"`, boolean-failed (`-32003`).

**Result:** `{ ai_id, wall_id, result_guid, status: "cut" }`.

#### `ops.opening.modify`
Reads the wall's stored opening list, replaces the entry for `ai_id`, rebuilds the wall and re-cuts every opening on it.

#### `ops.opening.delete`
Required: `ai_id`. Removes the opening from the wall's spec and rebuilds.

### 3.4 Slabs — `ops.slab.*`

#### `ops.slab.create`

```json
{
  "method": "ops.slab.create",
  "params": {
    "ai_id": "SLAB_GF",
    "polygon": [[0,0],[6000,0],[6000,4000],[0,4000]],
    "thickness_mm": 150,
    "base_z_mm": 0,
    "top_or_bottom": "top",
    "tags": []
  }
}
```

| Param            | Type             | Required | Default | Notes |
|------------------|------------------|----------|---------|-------|
| `polygon`        | `[[x,y], ...]`   | **yes**  | —       | ≥ 3 points, mm. |
| `thickness_mm`   | number           | no       | 150     | |
| `base_z_mm`      | number           | no       | 0       | mm. |
| `top_or_bottom`  | `"top"\|"bottom"`| no       | `"top"` | `"top"`: extrudes downward from `base_z`. `"bottom"`: upward. |

**Errors:** `"Need at least 3 points for slab"`.

#### `ops.slab.delete`
Required: `ai_id`.

### 3.5 Roofs — `ops.roof.*`

#### `ops.roof.create`

```json
{
  "method": "ops.roof.create",
  "params": {
    "ai_id": "ROOF_1",
    "kind": "gable",
    "footprint": [[0,0],[6000,0],[6000,4000],[0,4000]],
    "pitch_deg": 30,
    "ridge_height_mm": 1500,
    "eave_overhang_mm": 300,
    "base_z_mm": 2700,
    "tags": []
  }
}
```

| Param              | Type     | Required | Default  | Notes |
|--------------------|----------|----------|----------|-------|
| `kind`             | string   | no       | `"gable"`| `"flat"` \| `"shed"` \| `"gable"` \| `"hip"`. |
| `footprint`        | `[[x,y], ...]` | **yes** | — | ≥ 3 points, mm. |
| `pitch_deg`        | number   | no       | 30       | Degrees. Ignored for `"flat"`. |
| `ridge_height_mm`  | number   | no       | 0        | Used for `"flat"` (= thickness) and `"gable"`/`"hip"` (= ridge above eave). |
| `eave_overhang_mm` | number   | no       | 0        | Outward offset (approximation; AI may pre-overhang the footprint). |
| `base_z_mm`        | number   | no       | 0        | Eave height. |

**Errors:** `"footprint must have at least 3 points"`, `"Unknown roof kind: <kind>"`.

#### `ops.roof.delete`
Required: `ai_id`.

### 3.6 Primitives — `ops.primitive.*`

#### `ops.primitive.create`

```json
{
  "method": "ops.primitive.create",
  "params": {
    "ai_id": "BOX_1",
    "kind": "box",
    "dimensions": { "width_mm": 1000, "depth_mm": 1000, "height_mm": 1000 },
    "transform":  { "position_mm": [0, 0, 0], "rotation_deg": 0 },
    "tags": []
  }
}
```

| Param        | Type   | Required | Notes |
|--------------|--------|----------|-------|
| `kind`       | string | **yes**  | `"box"` \| `"cylinder"` \| `"sphere"` \| `"prism"`. |
| `dimensions` | object | **yes**  | Shape-dependent: `box {width_mm, depth_mm, height_mm}`, `cylinder {radius_mm, height_mm}`, `sphere {radius_mm}`. |
| `transform`  | object | no       | `{ position_mm: [x,y,z], rotation_deg: <z-axis>}`. |

### 3.7 Components — `ops.component.*`

| Method | Purpose | Required params |
|--------|---------|-----------------|
| `ops.component.place`  | Insert a component instance | `ai_id`, `definition` (path or library name), `transform.position_mm`, `transform.rotation_deg` |
| `ops.component.delete` | Remove an instance         | `ai_id` |

### 3.8 Materials & Layers — `ops.material.*`, `ops.layer.*`

#### `ops.material.upsert`
```json
{ "id": "BRICK_RED", "color_hex": "B22222", "alpha": 1.0 }
```
| Param       | Type   | Required | Notes |
|-------------|--------|----------|-------|
| `id`        | string | yes      | Material ai_id; also used as SketchUp material name. |
| `color_hex` | string | yes      | `"RRGGBB"` (no leading `#`). |
| `alpha`     | number | no (1.0) | 0..1. |

**Errors:** `"id is required"`, `"color_hex is required"`.
**Result:** `{ id, status: "upserted", rgb: [r, g, b] }`.

#### `ops.material.assign`
```json
{ "material_id": "BRICK_RED", "target_ids": ["W1", "W2"] }
```
**Result:** `{ applied: ["W1"], missing: ["W2"], status: "ok" }` — partial success is normal; check `missing`.

#### `ops.layer.upsert` / `ops.layer.assign`
Same shape pattern as materials. `id` (or `name`), `color: [r,g,b]`, `visible: bool`.

### 3.9 Batch — `ops.batch`

**Use this whenever you build more than one entity.** Fewer round-trips, shared `start_operation`, single undo step for the user.

```json
{
  "jsonrpc": "2.0",
  "id": "build-1",
  "method": "ops.batch",
  "params": {
    "mode": "atomic",
    "ops": [
      { "method": "ops.wall.create",  "params": { "ai_id": "W1", "centerline": [[0,0],[6000,0]], "height_mm": 2700, "thickness_mm": 200 } },
      { "method": "ops.wall.create",  "params": { "ai_id": "W2", "centerline": [[6000,0],[6000,4000]], "height_mm": 2700, "thickness_mm": 200 } },
      { "method": "ops.opening.cut",  "params": { "ai_id": "DOOR_1", "wall_id": "W1", "offset_mm": 1500, "width_mm": 900, "height_mm": 2100 } },
      { "method": "ops.slab.create",  "params": { "ai_id": "SLAB_GF", "polygon": [[0,0],[6000,0],[6000,4000],[0,4000]], "thickness_mm": 150 } }
    ]
  }
}
```

#### `mode` field

| Value | Default | Behaviour |
|-------|---------|-----------|
| `"atomic"` | yes | All sub-ops share one `start_operation`. **Any failure aborts the entire batch** (`abort_operation`) — no partial state is committed. Returns a JSON-RPC protocol-level error. |
| `"best_effort"` | no | Each sub-op runs independently. Failures become **inline error entries** in the result array (same index position). Successfully completed ops are committed; failed ops are skipped. |

**When to use `"best_effort"`:** AI retry flows, large model builds where one bad op (e.g. a zero-length wall) should not discard the other 30 walls. The caller inspects `results[i]["error"]` to determine which ops need retrying.

**Atomic result** — array of sub-op results in input order (or a JSON-RPC error on failure):
```json
[
  { "ai_id": "W1", "guid": "...", "status": "created" },
  { "ai_id": "W2", "guid": "...", "status": "created" },
  { "ai_id": "DOOR_1", "wall_id": "W1", "status": "cut" },
  { "ai_id": "SLAB_GF", "guid": "...", "status": "created" }
]
```

**Best-effort result** — failures are inline, not exceptions:
```json
[
  { "ai_id": "W1", "guid": "...", "status": "created" },
  { "error": "zero-length wall", "index": 1, "method": "ops.wall.create" },
  { "ai_id": "DOOR_1", "wall_id": "W1", "status": "cut" }
]
```

**Notes:**
- Sub-op domain errors (e.g. `{ "error": "Wall not found" }`) **also abort** atomic batches — they are treated the same as Ruby exceptions.
- Sub-op errors include the failing index: `"Batch failed at index 2 (ops.opening.cut): Wall not found: W1"`.
- `ops.batch` as a sub-op of another `ops.batch` is not supported (no nesting).

### 3.10 Captures — `view.*`

| Method | Purpose | Key params |
|--------|---------|-----------|
| `view.capture`           | Snap one view to PNG → transcoded WebP | `preset` (`"iso"`, `"front"`, ...), `width`, `height` |
| `view.capture_canonical` | All 6 canonical views                  | `width`, `height` |
| `view.walkthrough`       | Generate animation                     | `preset` (`"orbit"`, `"flythrough"`, `"cinematic"`), `frames`, `fps` |

### 3.11 Queries — `query.*`

| Method | Purpose |
|--------|---------|
| `query.scene_summary`  | Token-efficient digest of model contents |
| `query.deep_scan`      | Full recursive introspection with metadata (paginated) |
| `query.export_json`    | Export the full model graph as JSON |
| `query.verify`         | Confirm a list of `ai_id`s exist in the model |
| `query.entity`         | Inspect one entity by `ai_id` |
| `query.cache_stats`    | `AI_ID` cache hit/miss counters |
| `query.clash_detect`   | AABB overlap analysis with severity grading |

#### `query.deep_scan` — params (Phase 3)

```json
{
  "method": "query.deep_scan",
  "params": {
    "limit":         25,
    "offset":        0,
    "include_attrs": true,
    "type_filter":   "wall"
  }
}
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `limit` | int | null (all) | Max entities per page. Use 25–100 for large models. |
| `offset` | int | 0 | Skip first N entities. Combine with `limit` to paginate. |
| `include_attrs` | bool | false | Embed all non-internal attribute dicts inline under `"attrs"`. Eliminates N+1 `query.attr.get` calls. |
| `type_filter` | string | null | Only return entities of this type (`"wall"`, `"slab"`, `"roof"`, etc.). |

**Response** includes a `"page"` envelope alongside `"entities"` and `"summary"`:

```json
{
  "entities": [...],
  "summary": { "total_count": 200, "total_entities": 25, ... },
  "page": { "offset": 0, "limit": 25, "returned": 25, "total": 200, "has_more": true }
}
```

Iterate by incrementing `offset` by `limit` until `has_more` is `false`.

#### `query.attr.find` — params (Phase 3)

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `dict_name` | string | required | Dictionary to search (e.g. `"bim"`). |
| `key` | string | required | Attribute key that must exist. |
| `value` | string | null | If set, key must equal this value. |
| `type` | string | null | Entity type filter (`"wall"`, etc.). |
| `limit` | int | null | Stop after N matches (early exit — faster on large models). |
| `depth` | int | null | Max recursion depth into nested groups/components. |

Response includes `"limit_applied": true` when a limit was used.

### 3.12 Lifecycle — `lifecycle.*`

| Method | Purpose | Params |
|--------|---------|--------|
| `lifecycle.save`       | Save current file | optional `path` |
| `lifecycle.save_as`    | Save to new path  | `path` |
| `lifecycle.new`        | New empty file    | — |
| `lifecycle.open`       | Open `.skp`       | `path` |
| `lifecycle.close`      | Close model       | — |
| `lifecycle.model_info` | Title, path, modified flag, entity count | — |

### 3.13 Dimensions — `ops.dimension.create`

Creates an annotation dimension between two `ai_id`s or two `[x,y,z]` points (mm). See [ops/dimension.rb](../ruby_plugin/su_mcp_bridge/ops/dimension.rb).

---

## 4. Phase 2 — Metadata DB (implemented)

The vision document calls for treating SketchUp models like a relational database. The `query.attr.*` and `ops.attr.*` namespace is now fully implemented. See [ruby_plugin/su_mcp_bridge/ops/attr.rb](../ruby_plugin/su_mcp_bridge/ops/attr.rb) and the corresponding MCP tools in `server.py`.

| Method | Handler | Purpose |
|--------|---------|---------|
| `query.attr.get`    | `Ops::Attr.get`      | Read one key or full dict from an entity |
| `query.attr.list`   | `Ops::Attr.list`     | List all dictionary names on an entity |
| `query.attr.find`   | `Ops::Attr.find`     | Scan all entities for predicate match |
| `ops.attr.set`      | `Ops::Attr.set`      | Write one key into a dict |
| `ops.attr.set_bulk` | `Ops::Attr.set_bulk` | Atomic multi-entity, multi-key write |

**The standard BIM dictionary** is `"bim"` — see [docs/bim_metadata_schema.md](bim_metadata_schema.md) for the full key reference (structural_role, material_spec, fire_rating, ifc_class, cost_per_unit, quantity_basis, load_kpa, notes).

**Reserved internal dictionary:** `"su_mcp_bridge"` — written by SAIE ops (wall_spec, roof_spec, type, ai_id, openings_list). Never write into this dictionary from external code.

**Report integration:** `generate_model_report()` and `generate_csv_inventory()` in `core/report.py` now accept an optional `bim_data` argument (`{ai_id: {key: value}}`). When provided, reports include a BIM Data section and a Quantity Takeoff table with grand total.

---

## 5. Compliance checklist for new ops

When adding a new op, verify:

- [ ] Method name follows `<domain>.<entity>.<verb>` (e.g. `ops.window.create`).
- [ ] Registered in `build_handlers` in [ruby_plugin/su_mcp_bridge/main.rb](../ruby_plugin/su_mcp_bridge/main.rb).
- [ ] All linear params are `*_mm`, all angles are `*_deg`.
- [ ] Coordinates are 2D `[x,y]` for footprints/centerlines, 3D `[x,y,z]` for transforms.
- [ ] Accepts `ai_id` (preferred) or `id` (back-compat) for create; **requires** it for modify/delete.
- [ ] Auto-generates `ai_id` via `SUMCPBridge::AI_ID.auto_name(...)` when omitted on create.
- [ ] Returns `{ ai_id, guid, status, bounds }` on create; `{ ai_id, status: "deleted"|"modified" }` on mutation.
- [ ] Domain errors returned as `{ "error": "<message>" }` inside `result`.
- [ ] Wraps SketchUp mutations in `model.start_operation` / `commit_operation` (or relies on outer batch).
- [ ] Persists reconstruction params via `group.set_attribute("su_mcp_bridge", "<entity>_spec", params)` so the entity can be rebuilt.
- [ ] Tags entity with type via `group.set_attribute("su_mcp_bridge", "type", "<entity>")`.
- [ ] Has a corresponding MCP tool in `src/su_mcp_bridge/mcp_server/server.py`.
- [ ] Unit test in `tests/unit/`.

---

## 6. Open questions

These are unresolved decisions from Phase 1 that need owner input before Phase 2:

1. ~~**Bounds units in `result`.**~~ **Resolved (v3.0):** `bounds.min` and `bounds.max` in create results are now mm (`v * 25.4`, 3 decimal places). Previously leaked SketchUp-native inches.
2. ~~**Idempotency keys.**~~ **Resolved (v3.0):** All `create` ops (wall, slab, roof, primitive) now upsert when a named `ai_id` already exists — the existing entity is erased and rebuilt atomically, and `result.status` is `"upserted"` instead of `"created"`. Auto-generated ids (no `ai_id` in params) always create fresh. Materials already upserted; now consistent.
3. ~~**Batch isolation.**~~ **Resolved (v3.0):** `mode: "atomic" | "best_effort"` is implemented in `ops.batch`. See §3.9.
4. **Sub-batch nesting.** `ops.batch` as a sub-op is currently an error (`"Unknown method: ops.batch"` since the handler isn't self-referential). Options: silently flatten the nested ops array, or document it as an explicit constraint.
5. **Versioning.** Add a `protocol_version` field to every request to enable schema evolution without breaking older clients? `hello` already returns the server's version; the open question is whether clients should echo it back on every call.
