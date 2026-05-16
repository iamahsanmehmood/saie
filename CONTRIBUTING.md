# Contributing to SAIE (SketchUp Automation & Intelligence Engine)

Thank you for considering contributing! This guide will help you get started.

> Note: the Python package directory is still named `su_mcp_bridge/` and the CLI binary is `sb` for backward compatibility. SAIE is the project's display name; internal identifiers are unchanged.

## 🛠️ Development Setup

### Prerequisites

- **Python 3.10+**
- **SketchUp 2025**
- **Git**

### 1. Clone and Install

```bash
git clone https://github.com/iamahsanmehmood/su-mcp-bridge.git
cd su-mcp-bridge
pip install -e ".[dev]"
```

### 2. Deploy Ruby Plugin

```powershell
# Windows PowerShell (Run as Administrator)
New-Item -ItemType Junction `
  -Path "$env:APPDATA\SketchUp\SketchUp 2025\SketchUp\Plugins\su_mcp_bridge" `
  -Target "<repo-path>\ruby_plugin\su_mcp_bridge"

Copy-Item "<repo-path>\ruby_plugin\su_mcp_bridge.rb" `
  "$env:APPDATA\SketchUp\SketchUp 2025\SketchUp\Plugins\"
```

### 3. Verify

```bash
# Start SketchUp, then:
sb ping
# Expected: PONG  plugin_v1.0.0
```

---

## 🧪 Running Tests

```bash
# Unit tests
pytest tests/unit -v

# With coverage
pytest tests/unit --cov=su_mcp_bridge --cov-report=term-missing

# Single file
pytest tests/unit/test_geometry.py -v
```

---

## 📁 Project Structure

```
su-mcp-bridge/
├── ruby_plugin/                 # SketchUp extension
│   ├── su_mcp_bridge.rb         # Extension loader
│   └── su_mcp_bridge/
│       ├── main.rb              # Server + handler registry
│       ├── transport.rb         # WebSocket server
│       ├── ai_id.rb             # Entity cache
│       ├── logger.rb            # Logger + subscribers
│       ├── dashboard.rb         # HTML UI
│       └── ops/                 # Operation handlers
│           ├── wall.rb, opening.rb, slab.rb, roof.rb
│           ├── primitive.rb, component.rb, material.rb
│           ├── capture.rb, animation.rb, dimension.rb
│           ├── query.rb, lifecycle.rb, clash.rb
│           └── ...
├── src/su_mcp_bridge/           # Python package
│   ├── core/                    # Geometry, reports, projects, lifecycle
│   ├── transport/               # WebSocket client
│   ├── mcp_server/              # MCP server (40+ tools)
│   ├── api_agent/               # Claude + Ollama agents
│   ├── cli/                     # sb CLI tool
│   └── parser/                  # DXF parser
├── tests/                       # Test suite
├── docs/                        # Documentation
├── scratch/                     # Test/demo scripts
└── README.md
```

---

## 🎨 Code Style

### Python
- **Formatter**: `black` (line length 100)
- **Linter**: `ruff`
- **Type hints**: Required for all public functions
- **Docstrings**: Google-style

### Ruby
- **Style**: SketchUp Ruby API conventions
- **Naming**: `snake_case` for methods, `UPPER_CASE` for constants
- **Module structure**: All ops under `SUMCPBridge::Ops::*`

---

## 🔄 Adding a New Operation

### 1. Ruby Handler

Create `ruby_plugin/su_mcp_bridge/ops/my_op.rb`:
```ruby
module SUMCPBridge
  module Ops
    module MyOp
      def self.create(params)
        # ... SketchUp API calls ...
        { "ai_id" => params["ai_id"], "status" => "created" }
      end
    end
  end
end
```

### 2. Register in `main.rb`

```ruby
require_relative 'ops/my_op'
# In build_handlers:
"ops.my_op.create" => ->(p) { Ops::MyOp.create(p) },
```

### 3. MCP Tool in `server.py`

```python
@mcp.tool()
def create_my_op(ai_id: str, ...) -> str:
    result = _call("ops.my_op.create", {"ai_id": ai_id, ...})
    return json.dumps(result, indent=2)
```

### 4. CLI Command in `sb.py`

Add parser entry + handler function + DISPATCH entry.

### 5. Tests

Add `tests/unit/test_my_op.py`.

---

## 📝 Pull Request Checklist

- [ ] All tests pass (`pytest tests/unit`)
- [ ] New handler registered in `main.rb`
- [ ] MCP tool added to `server.py` with docstring
- [ ] CLI command added (if user-facing)
- [ ] `docs/ARCHITECTURE.md` updated with new method
- [ ] No hardcoded paths (use env vars or config)
- [ ] Error handling: return `{"error": "..."}` on failure

---

## 🐛 Debugging

### Ruby Console
Open SketchUp → Extensions → SAIE (SU MCP Bridge) → Ruby Console

### Dashboard
Extensions → SAIE (SU MCP Bridge) → Dashboard & Logs

### Python Logging
```bash
SU_MCP_BRIDGE_LOG=DEBUG sb status
```

---

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.
