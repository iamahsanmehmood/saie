# Architecture — SAIE (SketchUp Automation & Intelligence Engine)

## System Overview

SAIE follows a **declarative data contract** architecture. The AI decides *what* to build, Python calculates *precise geometry*, and SketchUp executes *native Ruby operations*.

> Project formerly known as "SU MCP Bridge". The Python package, Ruby plugin folder, and CLI binary still use the original names (`su_mcp_bridge`, `sb`) for backward compatibility — these will be revisited in a future scalability phase.

```
┌─────────────────────────────────────────────────────────┐
│  AI Layer (Claude, Ollama, MCP Client)                  │
│    ↓ Tool calls / natural language                      │
├─────────────────────────────────────────────────────────┤
│  Python Layer                                           │
│  ├── api_agent/    — Agent loops (Claude + Ollama)      │
│  ├── mcp_server/   — MCP stdio server (40+ tools)      │
│  ├── cli/          — sb CLI (20+ commands)              │
│  ├── core/         — Geometry, reports, projects        │
│  ├── transport/    — WebSocket JSON-RPC client          │
│  └── parser/       — DXF import                         │
│    ↓ JSON-RPC 2.0 over WebSocket                        │
├─────────────────────────────────────────────────────────┤
│  Ruby Layer (SketchUp Plugin)                           │
│  ├── main.rb       — Server, handler registry           │
│  ├── transport.rb  — WebSocket server (ws://0.0.0.0:9876) │
│  ├── ai_id.rb      — Entity tracker (ai_id → entity)   │
│  ├── ops/          — Operation handlers                 │
│  │   ├── wall.rb, opening.rb, slab.rb, roof.rb         │
│  │   ├── primitive.rb, component.rb, material.rb       │
│  │   ├── capture.rb, animation.rb, dimension.rb        │
│  │   ├── query.rb (export, deep_scan, verify)          │
│  │   ├── lifecycle.rb (save, open, close)              │
│  │   └── clash.rb (AABB overlap detection)             │
│  ├── dashboard.rb  — HTML UI for live monitoring        │
│  └── logger.rb     — Log + subscriber system            │
│    ↓ SketchUp Ruby API                                  │
├─────────────────────────────────────────────────────────┤
│  SketchUp 2025                                          │
└─────────────────────────────────────────────────────────┘
```

## JSON-RPC Method Registry (v3.0)

### System
| Method | Handler | Description |
|--------|---------|-------------|
| `ping` | `Server#handle_ping` | Connectivity test |
| `hello` | `Server#handle_hello` | Handshake, returns capabilities |

### Walls & Openings
| Method | Handler | Description |
|--------|---------|-------------|
| `ops.wall.create` | `Ops::Wall.create` | Create wall from centerline |
| `ops.wall.modify` | `Ops::Wall.modify` | Modify existing wall |
| `ops.wall.delete` | `Ops::Wall.delete` | Delete wall by ai_id |
| `ops.opening.cut` | `Ops::Opening.cut` | Cut door/window opening |
| `ops.opening.modify` | `Ops::Opening.modify` | Modify opening params |
| `ops.opening.delete` | `Ops::Opening.delete` | Delete opening |

### Geometry
| Method | Handler | Description |
|--------|---------|-------------|
| `ops.slab.create` | `Ops::Slab.create` | Floor/ceiling slab from polygon |
| `ops.roof.create` | `Ops::Roof.create` | Roof (flat, shed, gable, hip) |
| `ops.roof.delete` | `Ops::Roof.delete` | Delete roof |
| `ops.primitive.create` | `Ops::PrimitiveOps.create` | Box, sphere, cylinder, etc. |

### Components & Materials
| Method | Handler | Description |
|--------|---------|-------------|
| `ops.component.place` | `Ops::Component.place` | Place component |
| `ops.component.delete` | `Ops::Component.delete` | Delete component |
| `ops.material.upsert` | `Ops::Material.upsert` | Create/update material |
| `ops.material.assign` | `Ops::Material.assign` | Assign material to entities |
| `ops.layer.upsert` | `Ops::Layer.upsert` | Create/update layer |
| `ops.layer.assign` | `Ops::Layer.assign` | Assign entities to layer |

### Batch & Lifecycle
| Method | Handler | Description |
|--------|---------|-------------|
| `ops.batch` | `Server#handle_batch` | Atomic multi-op (single undo) |
| `ops.clear_model` | `Ops::Capture.clear_model` | Delete all + reset cache |
| `ops.delete` | `Ops::Query.delete` | Generic delete by ai_id |
| `lifecycle.save` | `Ops::Lifecycle.save` | Save model |
| `lifecycle.save_as` | `Ops::Lifecycle.save_as` | Save to new path |
| `lifecycle.new` | `Ops::Lifecycle.new_file` | New empty model |
| `lifecycle.open` | `Ops::Lifecycle.open_file` | Open .skp file |
| `lifecycle.close` | `Ops::Lifecycle.close` | Close SketchUp |
| `lifecycle.model_info` | `Ops::Lifecycle.model_info` | Model metadata |

### Queries
| Method | Handler | Description |
|--------|---------|-------------|
| `query.scene_summary` | `Ops::Query.scene_summary` | ~200 token digest |
| `query.export_json` | `Ops::Query.export_json` | Full model state |
| `query.deep_scan` | `Ops::Query.deep_scan` | Recursive introspection |
| `query.entity` | `Ops::Query.entity` | Single entity details |
| `query.verify` | `Ops::Query.verify` | Verify ai_ids exist |
| `query.clash_detect` | `Ops::Clash.detect` | AABB overlap detection |
| `query.cache_stats` | `AI_ID.stats` | Cache statistics |

### Views & Animation
| Method | Handler | Description |
|--------|---------|-------------|
| `view.capture` | `Ops::Capture.take` | Single screenshot |
| `view.capture_canonical` | `Ops::Capture.canonical` | All 6 views |
| `view.walkthrough` | `Ops::Animation.walkthrough` | Multi-frame animation |

### Dimensions
| Method | Handler | Description |
|--------|---------|-------------|
| `ops.dimension.create` | `Ops::Dimension.create` | Linear dimension |

## Entity Lifecycle

```
Create (ops.wall.create)
  → ai_id stored in SketchUp attribute dictionary
  → AI_ID cache updated
  → Entity tracked with type, spec metadata

Modify (ops.wall.modify)
  → Old entity deleted
  → New entity created with same ai_id
  → Openings re-cut from stored specs

Delete (ops.delete)
  → Entity erased from model
  → AI_ID cache evicted
  → Verification can detect missing entities

Verify (query.verify)
  → Compare expected IDs vs actual model
  → Report found, missing, and orphans
```

## Wall Joining Algorithm

1. **Endpoint extraction**: Each wall contributes 2 endpoints
2. **Junction classification**: Group coincident endpoints, classify as L / T / Cross
3. **Through-wall selection**: Longest wall at each junction is the "through" wall
4. **Pullback calculation**: Abutting walls pulled back by `thickness/2 / sin(θ)`
5. **Acute angle clamping**: Angles < 30° capped to prevent extreme pullback
6. **Max pullback**: Never exceeds 90% of wall length

## Clash Detection Algorithm

1. Walk all AI-tracked entities, extract AABB bounding boxes
2. For each pair, test 3-axis AABB overlap (with tolerance)
3. Skip known parent-child relationships (wall ↔ opening)
4. Calculate overlap volume
5. Classify severity: `info` (< 0.01 in³), `warning` (< 1.0 in³), `error` (≥ 1.0 in³)
