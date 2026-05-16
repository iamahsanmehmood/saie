# Configuration Reference

SAIE has **one** configuration file, `saie.toml`. Both the Python MCP server and the Ruby SketchUp plugin read from it, so ports and paths cannot drift apart.

---

## Resolution Order

The first file that exists wins:

| # | Location | When to use |
|---|---|---|
| 1 | `$SAIE_CONFIG` (env var) | CI, ad-hoc overrides, per-shell switches |
| 2 | `./saie.toml` (current working dir) | Per-project overrides |
| 3 | `~/.saie/saie.toml` | **Recommended for end users.** Created by the installer. |
| 4 | `<install-root>/saie.toml` | Bundled defaults — always present, never edit. |

To find which file is currently being used: open SketchUp's SAIE Dashboard → **Config** tab → look at *Resolved from*. Or from the CLI:

```bash
saie config show
```

---

## Environment Variable Overrides

**Every** TOML field can be overridden by an environment variable using the pattern:

```
SAIE_<SECTION>_<KEY>
```

Examples:

| Env var | Effect |
|---|---|
| `SAIE_BRIDGE_PORT=9999` | Bridge listens on 9999 instead of 9876 |
| `SAIE_STREAM_FPS=12` | Live stream targets 12 fps |
| `SAIE_AGENTS_DEFAULT_PROVIDER=ollama` | `saie agent` defaults to local Ollama |
| `SAIE_SECURITY_LOCALHOST_ONLY=false` | Bridge binds to all interfaces (DANGEROUS) |
| `SAIE_LOGGING_LEVEL=debug` | Verbose logs |

Booleans: `1`/`true`/`yes`/`on` are truthy; everything else is falsy.
Lists: comma-separated (e.g. `SAIE_PROJECTS_SUBDIRS=model,captures,reports`).

---

## Section Reference

### `[bridge]` — WebSocket JSON-RPC channel

| Key | Type | Default | Notes |
|---|---|---|---|
| `host` | string | `"127.0.0.1"` | **Keep localhost** unless you trust the LAN |
| `port` | int | `9876` | If busy, plugin scans up to `port + port_range` |
| `port_range` | int | `10` | Auto-fallback range |
| `port_file` | path | `~/.saie_port` | Plugin writes the chosen port here; CLI reads it |
| `timeout` | float | `30.0` | Seconds the Python client waits for a response |

### `[stream]` — HTTP MJPEG live view

| Key | Type | Default | Notes |
|---|---|---|---|
| `enabled` | bool | `true` | Set false to disable the stream server entirely |
| `port` | int | `9877` | Browser URL: `http://localhost:<port>/` |
| `port_range` | int | `10` | Same fallback behaviour as bridge |
| `source` | string | `"window"` | `window` = full framebuffer; `view` = clean offline render |
| `fps` | int | `5` | 1..30; higher = more main-thread stalls |
| `quality` | int | `70` | JPEG quality 1..100 |
| `width` | int | `800` | Honoured by `source = "view"` only |
| `height` | int | `600` | Honoured by `source = "view"` only |
| `cache_ms` | int | `100` | Frame reuse window for concurrent consumers |

### `[sketchup]` — SketchUp install detection

| Key | Type | Default | Notes |
|---|---|---|---|
| `version` | string | `"2025"` | Used to derive Plugins path |
| `install_path` | path | `""` | Optional explicit install dir |
| `plugins_path` | path | `""` | Optional explicit Plugins dir (overrides version) |
| `autostart_bridge` | bool | `true` | False = start manually from Extensions menu |

### `[projects]` — Per-project folder layout

| Key | Type | Default |
|---|---|---|
| `root` | path | `~/Documents/SAIE_Projects` |
| `subdirs` | list[str] | `["model", "captures", "reports", "data/scan_history", "assets"]` |

`saie project create "Name"` produces `<root>/Name_<date>/<subdirs>`.

### `[capture]` — Defaults for capture / render tools

| Key | Type | Default | Values |
|---|---|---|---|
| `default_preset` | string | `"iso"` | `plan` / `iso` / `elev_n` / `elev_s` / `elev_e` / `elev_w` |
| `default_resolution` | string | `"med"` | `low` (640) / `med` (1280) / `high` (1920) / `ultra` (3840) |
| `default_style` | string | `"default"` | `default` / `hidden_line` / `wireframe` / `shaded` / `shaded_tex` / `monochrome` / `xray` |
| `isolation_margin` | float | `0.15` | Bbox margin when isolating a single entity |

### `[agents]` — AI provider defaults

| Key | Type | Default |
|---|---|---|
| `default_provider` | string | `"anthropic"` (or `"ollama"`) |
| `default_anthropic_model` | string | `"claude-sonnet-4-5-20250929"` |
| `default_ollama_model` | string | `"gemma3:4b"` |
| `ollama_host` | string | `"http://localhost:11434"` |

### `[logging]`

| Key | Type | Default | Notes |
|---|---|---|---|
| `level` | string | `"info"` | `trace` / `debug` / `info` / `warn` / `error` |
| `ring_buffer_size` | int | `500` | In-memory log buffer shown in Dashboard |
| `file` | path | `""` | Mirror logs to disk (e.g. `~/.saie/saie.log`) |

### `[security]`

| Key | Type | Default | Notes |
|---|---|---|---|
| `localhost_only` | bool | `true` | If false, requires explicit `host` change |
| `auth_token` | string | `""` | When set, all RPC params must echo it |

### `[experimental]` — Feature flags

| Key | Type | Default | Effect when false |
|---|---|---|---|
| `enable_raw_ruby_exec` | bool | `true` | `execute_ruby` tool returns `disabled` |
| `enable_walkthrough_video` | bool | `true` | `generate_walkthrough` tool disabled |
| `enable_dxf_import` | bool | `true` | `parse_dxf_plan` tool disabled |

---

## Example: production hardening

```toml
[bridge]
host = "127.0.0.1"
port = 9876

[security]
localhost_only = true
auth_token = "REPLACE-WITH-A-LONG-RANDOM-STRING"

[experimental]
enable_raw_ruby_exec = false   # forbid arbitrary Ruby execution

[logging]
level = "warn"
file  = "~/.saie/saie.log"
```

---

## Example: development on a second monitor

```toml
[bridge]
port = 9876

[stream]
fps     = 15      # smooth-enough for demos
quality = 80
source  = "window"

[agents]
default_provider = "anthropic"
default_anthropic_model = "claude-opus-4-7"

[logging]
level = "debug"
```

---

## Editing at runtime

Most settings are read at startup. After editing `saie.toml`:

- **Bridge port / host:** restart SketchUp (or use Extensions → SAIE → Restart Server).
- **Stream port / FPS / quality / source:** call `configure_live_view` MCP tool (no restart) or restart SketchUp.
- **Agent defaults:** read fresh on every `saie agent` invocation (no restart).
- **Feature flags:** restart SketchUp.
