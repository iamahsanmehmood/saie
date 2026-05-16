# API Reference — JSON-RPC Methods

Complete reference for all JSON-RPC 2.0 methods supported by the SketchUp Ruby bridge.

**Transport**: WebSocket `ws://localhost:9876`
**Protocol**: JSON-RPC 2.0

## Request Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "ops.wall.create",
  "params": {
    "ai_id": "W1",
    "centerline": [[0, 0], [5000, 0]],
    "thickness_mm": 200,
    "height_mm": 2800
  }
}
```

## Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "ai_id": "W1",
    "status": "created"
  }
}
```

---

## System Methods

| Method | Params | Returns |
|--------|--------|---------|
| `ping` | — | `{pong, time, plugin_version}` |
| `hello` | — | `{name, version, protocol, methods[], capabilities{}}` |

## Wall Methods

| Method | Params | Returns |
|--------|--------|---------|
| `ops.wall.create` | `ai_id, centerline, thickness_mm, height_mm, layer?` | `{ai_id, status}` |
| `ops.wall.modify` | `ai_id, centerline?, thickness_mm?, height_mm?` | `{ai_id, status}` |
| `ops.wall.delete` | `ai_id` | `{ai_id, status}` |

## Opening Methods

| Method | Params | Returns |
|--------|--------|---------|
| `ops.opening.cut` | `wall_id, ai_id, offset_mm, width_mm, height_mm, sill_mm` | `{ai_id, status}` |
| `ops.opening.modify` | `wall_id, ai_id, offset_mm?, width_mm?, height_mm?, sill_mm?` | `{ai_id, status}` |
| `ops.opening.delete` | `wall_id, ai_id` | `{ai_id, status}` |

## Geometry Methods

| Method | Params | Returns |
|--------|--------|---------|
| `ops.slab.create` | `ai_id, polygon, thickness_mm, z_mm` | `{ai_id, status}` |
| `ops.roof.create` | `ai_id, polygon, roof_type, ridge_height_mm, z_mm` | `{ai_id, status}` |
| `ops.roof.delete` | `ai_id` | `{ai_id, status}` |
| `ops.primitive.create` | `ai_id, shape, ...shape_params` | `{ai_id, status}` |

## Component & Material Methods

| Method | Params | Returns |
|--------|--------|---------|
| `ops.component.place` | `ai_id, definition_name, position, rotation?` | `{ai_id, status}` |
| `ops.component.delete` | `ai_id` | `{ai_id, status}` |
| `ops.material.upsert` | `name, color, alpha?` | `{name, status}` |
| `ops.material.assign` | `ai_ids, material_name` | `{status}` |
| `ops.layer.upsert` | `name, visible?` | `{name, status}` |
| `ops.layer.assign` | `ai_ids, layer_name` | `{status}` |

## Batch & Control Methods

| Method | Params | Returns |
|--------|--------|---------|
| `ops.batch` | `operations[]` | `{results[], status}` |
| `ops.clear_model` | — | `{status}` |
| `ops.delete` | `ai_id` | `{ai_id, status}` |

## Lifecycle Methods

| Method | Params | Returns |
|--------|--------|---------|
| `lifecycle.save` | `path?` | `{status, path}` |
| `lifecycle.save_as` | `path` | `{status, path}` |
| `lifecycle.new` | — | `{status}` |
| `lifecycle.open` | `path` | `{status, path}` |
| `lifecycle.close` | — | `{status}` |
| `lifecycle.model_info` | — | `{title, path, modified, units, entity_count, ...}` |

## Query Methods

| Method | Params | Returns |
|--------|--------|---------|
| `query.scene_summary` | — | `{summary_text}` |
| `query.export_json` | — | `{entities[], total, type_counts}` |
| `query.deep_scan` | — | `{definitions[], entities[], summary{}}` |
| `query.entity` | `ai_id` | `{ai_id, type, bounds, ...}` |
| `query.verify` | `expected_ids[]` | `{found[], missing[], orphans[]}` |
| `query.clash_detect` | `tolerance_mm?` | `{clashes[], total, status}` |
| `query.cache_stats` | — | `{total, hits, misses}` |

## View Methods

| Method | Params | Returns |
|--------|--------|---------|
| `view.capture` | `preset, resolution?, save_dir?` | `{path, sidecar_json}` |
| `view.capture_canonical` | `resolution?, save_dir?` | `{paths{}}` |
| `view.walkthrough` | `preset?, frames?, fps?, resolution?, save_dir?` | `{save_dir, mp4?, status}` |

## Dimension Methods

| Method | Params | Returns |
|--------|--------|---------|
| `ops.dimension.create` | `start_point, end_point, offset_vector` | `{status}` |

---

## Error Response

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "Entity not found: W99"
  }
}
```

## Standard Error Codes
| Code | Meaning |
|------|---------|
| -32600 | Invalid request |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error |
