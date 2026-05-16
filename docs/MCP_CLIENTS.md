# MCP Client Setup

How to wire up SAIE in every major MCP host.

The common idea: every host needs to know **how to spawn the MCP server**. After `pip install saie`, the `saie-mcp` console script handles stdio transport — every host just needs one line pointing at it.

---

## Claude Desktop (Anthropic)

**Config file:**

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "saie": {
      "command": "saie-mcp"
    }
  }
}
```

Restart Claude Desktop. The 🔌 icon shows `saie` connected.

**With an explicit Python interpreter** (useful when `saie-mcp` isn't on PATH):

```json
{
  "mcpServers": {
    "saie": {
      "command": "C:/Users/Admin/.venvs/saie/Scripts/python.exe",
      "args": ["-m", "saie"]
    }
  }
}
```

---

## Claude Code (`claude` CLI)

```bash
claude mcp add saie -- saie-mcp
claude mcp list
```

Or in the user-level config file `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "saie": { "command": "saie-mcp" }
  }
}
```

---

## Cursor

**Config:** Settings → MCP → Edit `mcp.json`.

```json
{
  "mcpServers": {
    "saie": {
      "command": "saie-mcp"
    }
  }
}
```

Cursor will list `saie` under available tools in the agent panel. Approve once and it'll auto-allow subsequent calls.

---

## Cline (VS Code extension)

`Settings → Cline → MCP Servers → Add server`:

| Field | Value |
|---|---|
| Name | `saie` |
| Command | `saie-mcp` |
| Args | *(empty)* |
| Env | *(empty)* |

---

## Continue.dev

In `.continue/config.json`:

```json
{
  "mcp": {
    "servers": {
      "saie": { "command": "saie-mcp" }
    }
  }
}
```

---

## Antigravity (Anthropic)

SAIE is bundled. Open the integrations panel and toggle **SAIE — SketchUp** on. Antigravity will pick up `saie-mcp` from your active Python environment.

If using a non-default Python, set:

```toml
# antigravity/integrations.toml
[saie]
command = "C:/Users/Admin/.venvs/saie/Scripts/python.exe"
args    = ["-m", "saie"]
```

---

## Open Interpreter

```bash
interpreter --mcp-server saie:saie-mcp
```

---

## Custom (HTTP-mode hosts)

The default transport is **stdio**. For HTTP-mode MCP hosts (some IDE integrations, hosted sandboxes), run the server in HTTP mode:

```bash
saie-mcp --transport sse --host 127.0.0.1 --port 8765
```

Then point the host at `http://127.0.0.1:8765/sse`.

---

## Programmatic use (Anthropic Agent SDK)

```python
import asyncio
from anthropic import Anthropic
# Spawn saie-mcp via stdio, connect with the MCP Python SDK,
# and pass discovered tools into Anthropic's tool-use API.
# See examples/agent_sdk_demo.py for a full working example.
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Host shows `saie` as red / failed | Open the host's MCP log. Usually means `saie-mcp` isn't on PATH for the host's Python — set the full interpreter path as above. |
| `saie` tools list is empty | The MCP server started but couldn't reach the SketchUp bridge. Run `saie ping` in a terminal — if that fails, SketchUp isn't running or the plugin failed to load. |
| Tool calls time out | The default RPC timeout is 30 s. Large `deep_scan` or `generate_walkthrough` calls may exceed it — increase `[bridge].timeout` in `saie.toml`. |
| Multiple SketchUps confuse the host | Only one bridge per host. Stop one SketchUp or run them on different ports (`SAIE_BRIDGE_PORT=9876` vs `=19876`). |
