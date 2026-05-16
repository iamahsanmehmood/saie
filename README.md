<div align="center">

# SAIE

**SketchUp Automation & Intelligence Engine**

*The Model-Context-Protocol bridge between AI agents and SketchUp 2025.*

[![PyPI](https://img.shields.io/pypi/v/saie.svg?color=blue)](https://pypi.org/project/saie/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![SketchUp 2025](https://img.shields.io/badge/SketchUp-2025-red.svg)](https://www.sketchup.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://modelcontextprotocol.io/)
[![CI](https://github.com/iamahsanmehmood/saie/actions/workflows/ci.yml/badge.svg)](https://github.com/iamahsanmehmood/saie/actions)

</div>

---

SAIE lets **Claude, Cursor, Antigravity, Ollama, and any MCP client** drive SketchUp 2025 natively. AI agents can build walls, cut openings, place components, run clash detection, generate walkthroughs, and inspect any entity in the model — over a strict declarative JSON-RPC contract, **not** raw Ruby eval.

It ships:

- A **Python MCP server** (`saie-mcp`) — exposes **67+ tools** to any MCP-compatible host.
- A **Ruby SketchUp plugin** — runs inside SketchUp 2025, listens on a WebSocket, executes the tool calls.
- A **CLI** (`saie`) — 20+ commands for terminal control without an AI in the loop.
- A **live MJPEG stream** — watch the SketchUp viewport in any browser while the AI works.
- A **central config** — one `saie.toml` controls every port, path, and feature flag on both sides.

---

## ✨ Highlights

| Capability | What you can do |
|---|---|
| **Walls + openings** | Build walls with auto-resolved butt/T/cross joints, cut doors/windows with auto-generated frames. |
| **Slabs + roofs** | Polygon-based slabs at any Z; pitched/gable/shed/hip roofs with eaves. |
| **Components** | Place library components, set materials/layers, modify attributes in bulk. |
| **Live view stream** | HTTP MJPEG at `http://localhost:9877` — captures real framebuffer including axes, selection, gizmos. |
| **AI snapshots** | `view_snapshot` returns inline base64 JPEG; AI gets a fresh image every call. |
| **View control** | Orbit, zoom, pan, set/get camera, select/deselect, isolate/unisolate via MCP. |
| **Reports** | Markdown / CSV / JSON model reports; BIM metadata via persistent attribute dictionaries. |
| **Clash detection** | AABB overlap analysis with severity grading. |
| **Walkthroughs** | Orbital / fly-through / cinematic animations rendered to disk. |
| **HQ renders** | Up to 3840×2880 isometric or any preset. |
| **DXF import** | Parse 2D CAD floorplans and build them. |
| **Project system** | Per-project folders with auto-routed captures, reports, assets. |
| **BIM database** | Read/write attribute dictionaries on any entity — query, list, find, bulk-set. |

---

## 🏗️ Architecture

```
┌────────────────────┐      MCP stdio       ┌─────────────────┐
│  Claude Desktop    │ ────────────────────▶│                 │
│  Cursor / Cline    │                      │  saie-mcp       │
│  Antigravity       │                      │  (Python MCP    │
└────────────────────┘                      │   server)       │
                                            │                 │
┌────────────────────┐      direct WS       │                 │
│  saie  CLI         │ ────────────────────▶│                 │
└────────────────────┘                      │                 │
                                            │                 │
┌────────────────────┐      tool use        │                 │
│  Anthropic agent   │ ────────────────────▶│                 │
│  Ollama agent      │                      └────────┬────────┘
└────────────────────┘                               │
                                                    │ JSON-RPC 2.0
                                                    │ over WebSocket
                                                    ▼
                                            ┌─────────────────┐
                                            │  SketchUp 2025  │
                                            │  + Ruby plugin  │
                                            │  + MJPEG :9877  │
                                            └─────────────────┘
```

The Python side and Ruby side both read **`saie.toml`** — one config, two halves stay in sync.

---

## 🚀 Quick Start

### Prerequisites
- **SketchUp 2025** installed (Windows or macOS)
- **Python 3.10+**
- *Optional:* Anthropic API key OR Ollama (for AI agent commands)

### 1. Install

```bash
pip install saie
```

For a development install:

```bash
git clone https://github.com/iamahsanmehmood/saie.git
cd saie
pip install -e ".[dev,all]"
```

### 2. Install the SketchUp plugin

**Windows (PowerShell):**

```powershell
.\scripts\install_plugin.ps1
```

**macOS:**

```bash
./scripts/install_plugin.sh
```

The installer copies (or symlinks, in dev mode) the `ruby_plugin/` contents into your SketchUp Plugins directory and copies `saie.toml` to `~/.saie/saie.toml`.

For manual install instructions see [docs/INSTALL.md](docs/INSTALL.md).

### 3. Launch SketchUp 2025

The plugin auto-starts. You'll see a **SAIE** entry under `Extensions → SAIE`. The bridge listens on `ws://localhost:9876` by default.

### 4. Verify

```bash
saie ping
# → {"pong": true, "plugin_version": "1.0.0", ...}
```

### 5. Build something

```bash
# With Claude
export ANTHROPIC_API_KEY="sk-ant-..."
saie agent "Build a 6x6m room with a door on the south wall"

# With local Ollama
saie agent --provider ollama --model gemma3:4b "Draw a table with 4 legs"
```

### 6. Watch live

Open `http://localhost:9877/` in any browser to see the SketchUp viewport in real time — axes, selection highlights, the lot.

---

## 🔌 MCP client setup

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "saie": {
      "command": "saie-mcp"
    }
  }
}
```

### Cursor / Cline / Continue.dev

Same pattern — point them at the `saie-mcp` console script.

### Antigravity

SAIE is bundled as a first-class integration. See [docs/MCP_CLIENTS.md](docs/MCP_CLIENTS.md) for vendor-specific instructions.

### Anthropic Agent SDK (programmatic)

```python
import asyncio
from anthropic import Anthropic
from anthropic.types.beta import BetaMessageParam

# Spawn saie-mcp as a subprocess and connect via stdio.
# Full example: examples/agent_sdk_demo.py
```

---

## 🛠 CLI Reference

| Command | Purpose |
|---|---|
| `saie ping` | Test bridge connectivity |
| `saie status` | Bridge status + scene summary |
| `saie summary` | Token-efficient model digest |
| `saie scan` | Deep recursive scan |
| `saie report --format md\|csv\|json` | Generate model report |
| `saie clash` | Run clash detection |
| `saie verify W1 DOOR_1` | Confirm entity IDs exist |
| `saie capture [preset]` | Capture a view (plan/iso/elev_*) |
| `saie capture-all` | Capture all 6 canonical views |
| `saie render [preset]` | Ultra-HQ render (up to 3840×2880) |
| `saie walkthrough [preset]` | Orbital / flythrough / cinematic |
| `saie save [path]` | Save the model |
| `saie open <path>` | Open a .skp file |
| `saie project create\|list\|open\|info` | Project lifecycle |
| `saie agent "<prompt>"` | Anthropic agent |
| `saie agent --provider ollama "<prompt>"` | Local Ollama agent |
| `saie mcp` | Run the MCP server on stdio (same as `saie-mcp`) |

Full reference: [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md)

`sb` and `sketchup-mcp` are kept as legacy aliases so existing automations don't break.

---

## 📦 MCP Tools (67+)

Tools are exposed under the `mcp__saie__*` namespace. Highlights:

**Scene queries**
`ping` `hello` `scene_summary` `deep_scan` `model_info` `get_selection` `inspect_entity` `export_model_json` `verify_model`

**Geometry**
`create_wall` `modify_wall` `delete_wall` `cut_opening` `modify_opening` `delete_opening` `create_slab` `create_roof` `create_primitive` `place_component` `delete_entity`

**Materials & layers**
`upsert_material` `assign_material` `upsert_layer` `assign_layer`

**BIM metadata**
`get_entity_attribute` `list_entity_dictionaries` `find_entities_by_attribute` `set_entity_attribute` `set_entity_attributes_bulk`

**View control**
`orbit_view` `zoom_view` `zoom_extents` `zoom_selection` `pan_view` `set_camera` `get_camera` `select_entity` `deselect_entity` `clear_selection` `isolate_entity` `show_all`

**Captures & live view**
`view_snapshot` `capture_view` `capture_canonical` `capture_hq_render` `start_live_view` `stop_live_view` `live_view_status` `configure_live_view`

**Reports & analysis**
`generate_report` `detect_clashes` `parse_dxf_plan`

**Lifecycle**
`new_file` `open_file` `save_file` `save_as` `clear_model` `create_project` `set_active_project` `list_all_projects`

**Animation**
`generate_walkthrough`

**Batch / advanced**
`batch_operations` `execute_ruby` *(disable in production via `[experimental].enable_raw_ruby_exec = false`)*

Full tool reference with parameters and return types: [docs/MCP_TOOLS.md](docs/MCP_TOOLS.md)

---

## ⚙️ Configuration

Everything is controlled by **`saie.toml`**. The file is searched in this order:

1. `$SAIE_CONFIG` environment variable
2. `./saie.toml` in CWD
3. `~/.saie/saie.toml`
4. Repo-bundled default

Override any value with `SAIE_<SECTION>_<KEY>` env vars (e.g. `SAIE_BRIDGE_PORT=9999`).

| Section | Controls |
|---|---|
| `[bridge]` | WebSocket host/port, timeout, port-file path |
| `[stream]` | MJPEG port, FPS, JPEG quality, capture source |
| `[sketchup]` | SketchUp version, install path, plugin auto-start |
| `[projects]` | Project root directory and subfolder layout |
| `[capture]` | Default preset/resolution/style for captures |
| `[agents]` | Default AI provider, model names, Ollama endpoint |
| `[logging]` | Log level, ring-buffer size, optional log file |
| `[security]` | Localhost-only flag, optional auth token |
| `[experimental]` | Feature flags for `execute_ruby`, DXF import, walkthroughs |

Full reference: [docs/CONFIGURATION.md](docs/CONFIGURATION.md) · Port table: [docs/PORTS.md](docs/PORTS.md)

---

## 📚 Documentation

| Document | What it covers |
|---|---|
| [INSTALL.md](docs/INSTALL.md) | Per-platform install + uninstall |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Every `saie.toml` field |
| [PORTS.md](docs/PORTS.md) | All network ports SAIE uses |
| [MCP_TOOLS.md](docs/MCP_TOOLS.md) | Every MCP tool with parameters |
| [MCP_CLIENTS.md](docs/MCP_CLIENTS.md) | Claude Desktop, Cursor, Cline, Antigravity wiring |
| [CLI_REFERENCE.md](docs/CLI_REFERENCE.md) | All `saie` subcommands |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the bridge works |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | Python API for embedded use |
| [action_schema.md](docs/action_schema.md) | The declarative action contract |
| [bim_metadata_schema.md](docs/bim_metadata_schema.md) | BIM attribute conventions |
| [PUBLISHING.md](docs/PUBLISHING.md) | Releasing to PyPI / MCP registries |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev setup |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

---

## 🌐 Live View

Start streaming and watch SketchUp in any browser:

```bash
saie stream start --fps 8        # or via MCP: start_live_view
# → http://localhost:9877/
```

The stream reads SketchUp's own window buffer via Win32 GDI, so it includes everything you see on screen — coordinate axes, selection outlines, the rotate gizmo, inference tooltips — even when the SketchUp window is behind your browser.

---

## 🔒 Security model

- **Localhost by default.** The WebSocket listens on `127.0.0.1` only. Do not change `[bridge].host` to `0.0.0.0` on an untrusted network — anyone who can reach the port can modify your SketchUp model.
- **Optional shared token.** Set `[security].auth_token` and every request must echo it back. Useful when you must expose the bridge across a trusted LAN.
- **Raw Ruby eval is opt-in.** The `execute_ruby` tool is convenient for AI agents but executes arbitrary Ruby inside SketchUp. Disable it for shared / production use: `[experimental].enable_raw_ruby_exec = false`.

---

## 🧪 Development

```bash
# Clone + install dev deps
git clone https://github.com/iamahsanmehmood/saie.git
cd saie
pip install -e ".[dev,all]"

# Run unit tests
pytest tests/unit -v

# Run integration tests (requires SketchUp running with the plugin loaded)
pytest tests/integration -v -m integration

# Lint
ruff check src/

# Type-check
mypy src/saie src/su_mcp_bridge
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full dev guide.

---

## 📦 Publishing

SAIE publishes to:

- **PyPI** — `pip install saie`
- **GitHub Releases** — wheels + Ruby plugin zips
- **Anthropic MCP Registry** — listed for one-click Claude Desktop install
- **Smithery** — listed at <https://smithery.ai/server/saie>
- **mcp.so** — community MCP directory
- **Cline marketplace** — plugin install card

Release pipeline + manifests: [docs/PUBLISHING.md](docs/PUBLISHING.md)

---

## 📄 License

[MIT](LICENSE) — © 2026 Ahsan Mehmood.

## 👤 Author

**Ahsan Mehmood** — [@iamahsanmehmood](https://github.com/iamahsanmehmood)

---

<div align="center">

*If SAIE saves you time, please ⭐ the repo and let us know what you built.*

</div>
