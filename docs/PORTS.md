# Port Reference

SAIE uses **two** TCP ports, both bound to `127.0.0.1` by default. This page lists every port, what speaks on it, and how to change it.

---

## Port Table

| Port | Purpose | Protocol | Direction | Set in |
|---|---|---|---|---|
| **9876** | Bridge (JSON-RPC) | WebSocket | Python ↔ SketchUp | `[bridge].port` |
| **9877** | Live view stream | HTTP/MJPEG | Any browser → SketchUp | `[stream].port` |

Both ports auto-fall-back to the next free port if busy — search range is `port` to `port + port_range`. The plugin writes the actual port chosen to `~/.saie_port` (configurable via `[bridge].port_file`).

---

## 9876 — WebSocket Bridge

This is the **core RPC channel** between the Python MCP server and SketchUp.

**Protocol:** JSON-RPC 2.0 frames carried over a single persistent WebSocket connection.

**Speaker:** the Ruby plugin runs a tiny `TCPServer` inside SketchUp's main thread; the Python side uses the `websockets` library.

**Reachable by:**

- The Python MCP server (`saie-mcp`) — for serving tool calls from Claude / Cursor / Antigravity.
- The `saie` CLI — for direct commands like `saie ping` and `saie agent`.
- Any custom Python client using `from saie import SketchUpWSClient`.

**Closing the firewall:** the bridge binds to `127.0.0.1` only. Windows Firewall and macOS application firewalls do **not** prompt because no remote address can reach it. If you want to expose it to a trusted LAN:

```toml
[bridge]
host = "0.0.0.0"
[security]
localhost_only = false
auth_token = "long-random-string-here"
```

This is **discouraged unless you also set an auth token**: anyone reachable on `bridge.port` could modify your SketchUp model.

---

## 9877 — HTTP MJPEG Live View

A browser-friendly view of the SketchUp viewport.

**Protocol:** HTTP/1.1. Routes:

| Path | Returns |
|---|---|
| `/` | Minimal HTML viewer (`<img src="/stream">`) |
| `/stream` | `multipart/x-mixed-replace; boundary=sumcpframe` — continuous JPEG frames |
| `/snapshot.jpg` | A single fresh JPEG (one-shot) |
| `/healthz` | `200 OK` plain text `ok` |

**Started on demand** — the TCPServer isn't opened until you call `start_live_view` MCP tool, `saie stream start`, or click *Open Live View* in the Dashboard.

**Performance:** Each frame triggers a synchronous Win32 `BitBlt` from SketchUp's window DC on the main thread. At the default 5 fps that's ~200 ms between captures — fine for normal modeling. Going above 15 fps will cause visible stutter in heavy scenes.

**Capture sources:**

- `source = "window"` *(default)* — `GetWindowDC` + `BitBlt`. Captures SketchUp's real framebuffer including OpenGL overlays (axes, selection highlights, gizmos, inference tooltips). Works whether SketchUp is in the foreground or behind another window.
- `source = "view"` — `view.write_image`. Clean offline render at any requested resolution. **No** overlays; useful for AI inspection of pure geometry.

---

## Port Discovery

When the Ruby plugin can't bind to the configured port (e.g. you have two SketchUps open), it scans the next 10 ports and uses the first free one. Then it writes the chosen port to `~/.saie_port`:

```text
$ cat ~/.saie_port
9878
```

The Python client reads this file on connect, so your CLI / MCP server always finds the right port automatically. **Never commit this file** — it's already in `.gitignore`.

---

## Changing Ports

**Permanent change:**

```toml
# ~/.saie/saie.toml
[bridge]
port = 19876
[stream]
port = 19877
```

Then restart SketchUp.

**One-off change (e.g. CI):**

```bash
SAIE_BRIDGE_PORT=29876 SAIE_STREAM_PORT=29877 sketchup &
SAIE_BRIDGE_PORT=29876 saie ping
```

**Inside the Configure Port dialog:** `Extensions → SAIE → Configure Port...` writes the user-override into SketchUp's preference store; it takes precedence over `saie.toml`.

---

## Conflict Cheat Sheet

| Conflict | Resolution |
|---|---|
| Port already in use at startup | Auto-fallback to next free in range. Check `~/.saie_port` for actual port. |
| Two SketchUps both want 9876 | First one wins; second falls back to 9877+. The MJPEG server in the second SketchUp will also shift. |
| Corporate VPN reserves 9876 | Change `[bridge].port` to something in the 30000-40000 range. |
| Bridge and stream collide on same range | Both default ranges are 10, so they don't overlap (9876–9885 vs 9877–9886). If you customise, keep them separate. |
