# CLI Reference

Complete reference for the `sb` command-line tool.

## Usage

```
sb <command> [options] [arguments]
```

## System Commands

### `sb ping`
Test connectivity to the SketchUp bridge.
```bash
sb ping
# PONG  plugin_v1.0.0
```

### `sb status`
Show bridge status, plugin version, protocol version, and entity counts.
```bash
sb status
# Bridge:     connected
# Plugin:     v1.0.0
# Protocol:   v3.0
# Methods:    40+
# Entities:   8 AI-tracked
```

### `sb summary`
Token-efficient model digest (~200 tokens).

### `sb model-info`
Detailed model metadata: path, units, entity count, definitions, etc.

---

## Introspection Commands

### `sb scan`
Deep scan the model with full recursive introspection. Returns entity inventory with types, layers, materials, solid status, and geometry.
```bash
sb scan
# Deep Scan Complete
#   Entities:    15
#   Faces:       120
#   Edges:       180
#   Solids:      12
#   Non-Solids:  3
```

### `sb report`
Generate a structured model report.
```bash
sb report                       # Markdown report (default)
sb report --format csv          # CSV inventory
sb report --format json         # JSON snapshot
sb report --output ./reports    # Custom output directory
```

### `sb verify`
Verify that expected entity IDs exist in the model.
```bash
sb verify W1 W2 DOOR_1 SLAB_GF
```

### `sb clash`
Run AABB clash detection across all tracked entities.
```bash
sb clash
# Clash Detection: 0 clashes found (15 entities checked)
#   Model is clean!
```

---

## Capture Commands

### `sb capture`
Capture a single view from a preset camera angle.
```bash
sb capture iso                  # Isometric view
sb capture plan                 # Top-down plan
sb capture elev_n               # North elevation
sb capture iso -r high          # High resolution
sb capture plan -d ./output     # Custom directory
```

**Presets**: `plan`, `iso`, `elev_n`, `elev_e`, `elev_s`, `elev_w`
**Resolutions**: `low` (512×384), `med` (1024×768), `high` (1920×1440)

### `sb capture-all`
Capture all 6 canonical views in one command.

### `sb render`
Ultra-high-quality render (3840×2880).
```bash
sb render                       # ISO ultra render
sb render plan                  # Plan ultra render
sb render -d ./output           # Custom directory
```

### `sb walkthrough`
Generate a multi-frame camera animation.
```bash
sb walkthrough orbit                    # 360° aerial orbit
sb walkthrough flythrough               # Linear path
sb walkthrough cinematic                # Smooth arc
sb walkthrough orbit --frames 60        # Fewer frames
sb walkthrough orbit --fps 24           # 24fps output
sb walkthrough orbit -r high            # 1080p frames
```

---

## Lifecycle Commands

### `sb save`
Save the active model.
```bash
sb save                         # Save to current path
sb save C:/projects/house.skp   # Save to specific path
```

### `sb new`
Create a new empty SketchUp model.

### `sb open`
Open an existing .skp file.
```bash
sb open C:/projects/house.skp
```

### `sb clear`
Delete all entities and reset the ai_id cache.

---

## Project Commands

### `sb project create`
Create a new project with structured folder layout.
```bash
sb project create "My House"
```

### `sb project list`
List all projects in the default directory.

### `sb project open`
Open and set a project as active.
```bash
sb project open "My House"
```

### `sb project info`
Show details about the currently active project.

---

## Agent Commands

### `sb agent`
Start the AI agent in interactive mode or single-shot mode.
```bash
# Single-shot with Claude
sb agent "Build a 6x6m room with 4 walls"

# Interactive mode
sb agent

# Local Ollama
sb agent --provider ollama --model gemma4:e4b "Draw a table"

# Specify model
sb agent -m claude-3-5-sonnet-20241022 "Build a house"
```

### `sb mcp`
Start the MCP server (stdio transport) for Claude Desktop/Code integration.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SKETCHUP_HOST` | `localhost` | Bridge host |
| `SKETCHUP_PORT` | `9876` | Bridge port |
| `SKETCHUP_EXE` | Auto-detect | SketchUp executable path |
| `ANTHROPIC_API_KEY` | — | For Claude agent |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `SU_MCP_BRIDGE_LOG` | `INFO` | Log level (DEBUG/INFO/WARNING/ERROR) |
