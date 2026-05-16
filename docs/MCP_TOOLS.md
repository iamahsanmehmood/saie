# MCP Tools Reference

Complete reference for all MCP tools available when using SketchUp with Claude Desktop, Claude Code, or Antigravity.

## System Tools

### `ping`
Test bridge connectivity.
```json
{"pong": true, "plugin_version": "1.0.0"}
```

### `hello`
Handshake — returns full capability list.

### `scene_summary`
Token-efficient (~200 token) model digest. Use this first to understand the model.

### `deep_scan`
Comprehensive recursive model introspection. Returns:
- All `ComponentDefinition`s with face/edge counts
- All AI-tracked entities with metadata (type, layer, material, bounds, volume, solid status)
- Summary statistics

### `model_info`
Model metadata: path, title, units, entity count, definitions, materials, layers.

---

## Wall & Opening Tools

### `create_wall(ai_id, centerline, thickness_mm, height_mm, ...)`
| Param | Type | Required | Default |
|-------|------|----------|---------|
| `ai_id` | string | ✅ | — |
| `centerline` | `[[x1,y1],[x2,y2]]` | ✅ | — |
| `thickness_mm` | number | ❌ | 200 |
| `height_mm` | number | ❌ | 2800 |
| `layer` | string | ❌ | — |

### `modify_wall(ai_id, ...)`
Modify an existing wall. Same params as `create_wall`.

### `delete_wall(ai_id)`
Delete a wall by its `ai_id`.

### `cut_opening(wall_id, ai_id, offset_mm, width_mm, height_mm, sill_mm)`
Cut a door/window opening in a wall.
| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `wall_id` | string | ✅ | Parent wall |
| `ai_id` | string | ✅ | Opening ID |
| `offset_mm` | number | ✅ | From wall start |
| `width_mm` | number | ✅ | — |
| `height_mm` | number | ✅ | — |
| `sill_mm` | number | ❌ | 0 = door, 800+ = window |

### `modify_opening(wall_id, ai_id, ...)`
### `delete_opening(wall_id, ai_id)`

---

## Geometry Tools

### `create_slab(ai_id, polygon, thickness_mm, z_mm)`
Create a floor/ceiling slab from a polygon.

### `create_roof(ai_id, polygon, roof_type, ridge_height_mm, z_mm)`
Create a roof. Types: `flat`, `shed`, `gable`, `hip`.

### `create_primitive(ai_id, shape, ...)`
Create a primitive shape. Shapes: `box`, `sphere`, `cylinder`, `cone`, `prism`.

---

## Component & Material Tools

### `place_component(ai_id, definition_name, position, ...)`
### `upsert_material(name, color, alpha)`
### `assign_material(ai_ids, material_name)`

---

## Batch Operations

### `batch_operations(operations)`
Execute multiple operations atomically (single undo step).
```json
{
  "operations": [
    {"method": "ops.wall.create", "params": {"ai_id": "W1", ...}},
    {"method": "ops.wall.create", "params": {"ai_id": "W2", ...}}
  ]
}
```

---

## Query Tools

### `verify_model(expected_ids)`
Verify that expected entity IDs exist.

### `inspect_entity(ai_id)`
Get detailed info about a single entity.

### `export_model_json`
Export full model state as JSON.

### `detect_clashes(tolerance_mm?)`
AABB clash detection across all tracked entities.

---

## Capture & Render Tools

### `capture_view(preset, resolution?, save_dir?)`
Single screenshot. Presets: `plan`, `iso`, `elev_n/e/s/w`.

### `capture_canonical(resolution?, save_dir?)`
All 6 canonical views in one call.

### `capture_hq_render(preset?, resolution?, save_dir?)`
Ultra-quality render (3840×2880 default).

### `generate_walkthrough(preset?, frames?, fps?, resolution?)`
Automated camera animation. Presets: `orbit`, `flythrough`, `cinematic`.

---

## Lifecycle Tools

### `save_file(path?)`
Save the model. Optional path for "Save As".

### `save_as(path)`
Save to a new file path.

### `new_file()`
Create a new empty model.

### `open_file(path)`
Open an existing .skp file.

---

## Project Tools

### `create_project(name, base_dir?)`
Create a new project with structured folder layout.

### `list_all_projects(base_dir?)`
List all existing projects.

### `set_active_project(name, base_dir?)`
Open and activate a project. All outputs auto-route to its folders.

---

## Report Tools

### `generate_report(format?)`
Generate a model report. Formats: `md` (Markdown), `csv`, `json`.

---

## DXF Tools

### `parse_dxf_plan(filepath, layer_name?, default_thickness_mm?, default_height_mm?, scale_factor?)`
Parse a DXF file to extract wall centerlines.
