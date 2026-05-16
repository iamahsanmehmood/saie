# Installation

SAIE has **two pieces** that must both be installed:

1. The **Python package** (`pip install saie`) — provides `saie`, `saie-mcp`, `sb`, `sketchup-mcp` commands.
2. The **SketchUp Ruby plugin** — must be copied into SketchUp's Plugins directory so it auto-loads when SketchUp starts.

---

## Prerequisites

| | Version |
|---|---|
| **SketchUp** | 2025 (Pro or Studio). 2024 may work but isn't tested. |
| **Python** | 3.10 or newer |
| **OS** | Windows 10/11 or macOS 12+ |
| **Anthropic key** (optional) | Set `ANTHROPIC_API_KEY` for `saie agent` |
| **Ollama** (optional) | Run `ollama serve` for local agents |

---

## 1 — Python package

### From PyPI (recommended)

```bash
pip install saie
```

Optional extras:

```bash
pip install "saie[agent]"     # adds anthropic SDK
pip install "saie[ollama]"    # adds ollama client
pip install "saie[all]"       # both
pip install "saie[dev]"       # adds pytest/ruff/mypy
```

### From source

```bash
git clone https://github.com/iamahsanmehmood/saie.git
cd saie
pip install -e ".[dev,all]"
```

Editable installs are the right choice when developing the plugin too — every code change to `src/` takes effect on the next `saie` invocation.

### Verify

```bash
saie --help
saie-mcp --help
```

Both commands should print usage info.

---

## 2 — SketchUp Ruby plugin

The plugin folder is `ruby_plugin/su_mcp_bridge/` and the loader stub is `ruby_plugin/su_mcp_bridge.rb`. Both need to land in SketchUp's `Plugins` directory.

### Automatic install (recommended)

**Windows (PowerShell):**

```powershell
cd <repo-root>
.\scripts\install_plugin.ps1
```

**macOS:**

```bash
cd <repo-root>
./scripts/install_plugin.sh
```

The script:

1. Detects the SketchUp Plugins directory based on `[sketchup].version` in `saie.toml` (default `2025`).
2. Copies `ruby_plugin/su_mcp_bridge.rb` and the `ruby_plugin/su_mcp_bridge/` folder.
3. Creates `~/.saie/saie.toml` if it doesn't exist (a user-editable copy of the bundled defaults).

For development you can pass `--symlink` (PowerShell: `-Symlink`) to create junctions instead of copies — every edit in `ruby_plugin/` is picked up on the next SketchUp launch.

### Manual install

**Windows:**

| Source (in repo) | Destination |
|---|---|
| `ruby_plugin/su_mcp_bridge.rb` | `%APPDATA%\SketchUp\SketchUp 2025\SketchUp\Plugins\su_mcp_bridge.rb` |
| `ruby_plugin/su_mcp_bridge/` (entire folder) | `%APPDATA%\SketchUp\SketchUp 2025\SketchUp\Plugins\su_mcp_bridge\` |

**macOS:**

| Source | Destination |
|---|---|
| `ruby_plugin/su_mcp_bridge.rb` | `~/Library/Application Support/SketchUp 2025/SketchUp/Plugins/su_mcp_bridge.rb` |
| `ruby_plugin/su_mcp_bridge/` | `~/Library/Application Support/SketchUp 2025/SketchUp/Plugins/su_mcp_bridge/` |

---

## 3 — Launch SketchUp

Start SketchUp 2025. You should see:

- A new **`Extensions → SAIE`** menu with **Dashboard & Logs**, **Open Live View in Browser**, **Restart Server**, etc.
- A startup log line in the Ruby Console: `SU MCP Bridge Server started on port 9876 (v1.0.0)`.

---

## 4 — Verify the bridge

```bash
saie ping
```

Expected output:

```json
{"pong": true, "time": 1789..., "plugin_version": "1.0.0"}
```

If the ping times out:

- Check that the SketchUp Ruby Console (`Window → Ruby Console`) shows the startup line.
- Check that port 9876 isn't taken by another process — `netstat -an | findstr 9876` (Windows) or `lsof -i :9876` (macOS).
- If it's taken, edit `~/.saie/saie.toml` and change `[bridge].port`, then restart SketchUp.

---

## 5 — Wire up an MCP client

See [docs/MCP_CLIENTS.md](MCP_CLIENTS.md) for Claude Desktop, Cursor, Cline, and Antigravity setup.

For Claude Desktop the entry is one line:

```json
{ "mcpServers": { "saie": { "command": "saie-mcp" } } }
```

---

## Uninstall

```bash
pip uninstall saie
```

Then delete the plugin files from the SketchUp Plugins directory shown above, plus `~/.saie/` if you want to remove your user config.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `saie ping` returns `connection refused` | SketchUp isn't running, or the plugin failed to load. Open SketchUp's Ruby Console for errors. |
| Live stream shows Chrome instead of SketchUp | Already fixed in v1.0 — make sure you have the latest plugin files. The capture uses `GetWindowDC` for SketchUp's HWND, not the screen DC. |
| `saie agent` errors with auth | Set `ANTHROPIC_API_KEY` in your shell, or pass `--provider ollama`. |
| Multiple SketchUp installs (2024 + 2025) | Set `[sketchup].version = "2024"` in `saie.toml` or pass `SAIE_SKETCHUP_VERSION=2024`. |
