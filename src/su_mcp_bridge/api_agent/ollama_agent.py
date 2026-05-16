"""
api_agent/ollama_agent.py — Local Ollama-powered agent for SketchUp
====================================================================

Uses the OpenAI-compatible API that Ollama provides, so it works with
any model that supports tool calling (e.g. llama3.1, qwen2.5, mistral).

Usage:
    from su_mcp_bridge.api_agent.ollama_agent import OllamaAgent
    agent = OllamaAgent(model="qwen2.5:7b")
    agent.chat("Build a simple room with 4 walls")

Or via CLI:
    sb agent --provider ollama --model qwen2.5:7b "Build a room"

Environment:
    OLLAMA_HOST  — Ollama server URL (default: http://localhost:11434)
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from openai import OpenAI

# Ensure src/ is importable.
_src = os.path.join(os.path.dirname(__file__), "..", "..")
if _src not in sys.path:
    sys.path.insert(0, os.path.abspath(_src))

from su_mcp_bridge.core.logger import get_logger  # noqa: E402
from su_mcp_bridge.transport.ws_client import (  # noqa: E402
    BridgeConnectionError,
    BridgeError,
    BridgeTimeout,
    SketchUpWSClient,
)

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ping",
            "description": "Test connectivity to the SketchUp bridge.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_wall",
            "description": "Create a wall from centerline. All units in mm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ai_id": {"type": "string", "description": "Unique ID like 'W1'"},
                    "centerline": {"type": "array", "description": "[[x1,y1],[x2,y2]] in mm"},
                    "thickness_mm": {"type": "number"},
                    "height_mm": {"type": "number"},
                    "level": {"type": "string"},
                },
                "required": ["ai_id", "centerline"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_wall",
            "description": "Delete a wall by ai_id.",
            "parameters": {
                "type": "object",
                "properties": {"ai_id": {"type": "string"}},
                "required": ["ai_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cut_opening",
            "description": "Cut a door/window opening. sill_mm=0 for doors, ~900 for windows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ai_id": {"type": "string"},
                    "wall_id": {"type": "string"},
                    "offset_mm": {"type": "number"},
                    "width_mm": {"type": "number"},
                    "height_mm": {"type": "number"},
                    "sill_mm": {"type": "number"},
                },
                "required": ["ai_id", "wall_id", "offset_mm", "width_mm", "height_mm"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_slab",
            "description": "Create a floor slab from polygon in mm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ai_id": {"type": "string"},
                    "polygon": {"type": "array"},
                    "thickness_mm": {"type": "number"},
                    "base_z_mm": {"type": "number"},
                },
                "required": ["ai_id", "polygon"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_roof",
            "description": "Create a roof. Kinds: flat, shed, gable, hip.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ai_id": {"type": "string"},
                    "footprint": {"type": "array"},
                    "kind": {"type": "string"},
                    "pitch_deg": {"type": "number"},
                    "base_z_mm": {"type": "number"},
                },
                "required": ["ai_id", "footprint"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "batch_operations",
            "description": "Execute multiple ops atomically. Each: {method, params}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ops": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["ops"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_model",
            "description": "Delete all entities and reset.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_entity",
            "description": "Delete any entity by ai_id.",
            "parameters": {
                "type": "object",
                "properties": {"ai_id": {"type": "string"}},
                "required": ["ai_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upsert_material",
            "description": "Create/update a material. color_hex is 'RRGGBB'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "color_hex": {"type": "string"},
                    "alpha": {"type": "number"},
                },
                "required": ["id", "color_hex"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assign_material",
            "description": "Assign a material to multiple entities.",
            "parameters": {
                "type": "object",
                "properties": {
                    "material_id": {"type": "string"},
                    "target_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["material_id", "target_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scene_summary",
            "description": "Get model summary. Call this first.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_model",
            "description": "Verify expected ai_ids exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expected_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expected_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "capture_view",
            "description": "Screenshot. Presets: plan, iso, elev_n/e/s/w.",
            "parameters": {
                "type": "object",
                "properties": {
                    "preset": {"type": "string"},
                    "resolution": {"type": "string"},
                    "save_dir": {"type": "string"},
                },
                "required": ["preset"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "parse_dxf_plan",
            "description": "Parse a DXF file to extract wall centerlines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string"},
                    "layer_name": {"type": "string"},
                    "default_thickness_mm": {"type": "number"},
                    "default_height_mm": {"type": "number"},
                    "scale_factor": {"type": "number"},
                },
                "required": ["filepath"],
            },
        },
    },
    # -- v3.0 tools --
    {
        "type": "function",
        "function": {
            "name": "deep_scan",
            "description": "Comprehensive model scan returning all entities with metadata.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_clashes",
            "description": "Detect geometric clashes between tracked entities.",
            "parameters": {
                "type": "object",
                "properties": {"tolerance_mm": {"type": "number"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_file",
            "description": "Save the SketchUp model.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "model_info",
            "description": "Get model metadata.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_walkthrough",
            "description": "Generate camera walkthrough video. Presets: orbit, flythrough, cinematic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "preset": {"type": "string"},
                    "frames": {"type": "integer"},
                    "fps": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
]

# Map tool names -> JSON-RPC method names
_TOOL_TO_METHOD: dict[str, str] = {
    "ping": "ping",
    "create_wall": "ops.wall.create",
    "delete_wall": "ops.wall.delete",
    "cut_opening": "ops.opening.cut",
    "create_slab": "ops.slab.create",
    "create_roof": "ops.roof.create",
    "batch_operations": "ops.batch",
    "clear_model": "ops.clear_model",
    "delete_entity": "ops.delete",
    "upsert_material": "ops.material.upsert",
    "assign_material": "ops.material.assign",
    "scene_summary": "query.scene_summary",
    "verify_model": "query.verify",
    "capture_view": "view.capture",
    "parse_dxf_plan": "local.parse_dxf_plan",
    "list_layers": "query.list_layers",
    "deep_scan": "query.deep_scan",
    "detect_clashes": "query.clash_detect",
    "save_file": "lifecycle.save",
    "model_info": "lifecycle.model_info",
    "generate_walkthrough": "view.walkthrough",
}

# Import the rich architectural prompt and extra tools
try:
    from su_mcp_bridge.api_agent.architect_prompt import (
        ARCHITECT_SYSTEM_PROMPT as SYSTEM_PROMPT,
    )
    from su_mcp_bridge.api_agent.architect_prompt import (
        EXTRA_TOOL_MAP,
        EXTRA_TOOLS,
    )

    TOOLS.extend(EXTRA_TOOLS)
    _TOOL_TO_METHOD.update(EXTRA_TOOL_MAP)
except ImportError:
    SYSTEM_PROMPT = """\
You are an architectural modeler controlling SketchUp 2025 via tools.
All dimensions are in millimeters (mm). Entity IDs are unique strings like W1, DOOR_1, SLAB_GF.
Rules:
- Use centerline [[x1,y1],[x2,y2]] for walls
- sill_mm=0 for doors, 800-1200 for windows
- offset_mm + width_mm <= wall length
- Verify after building
Be precise and deterministic.
"""


class OllamaAgent:
    """Tool-use agent loop using Ollama's OpenAI-compatible API."""

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "",
        host: str = "localhost",
        port: int = 9876,
        max_turns: int = 20,
        verbose: bool = True,
    ):
        ollama_host = base_url or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.client = OpenAI(
            base_url=f"{ollama_host}/v1",
            api_key="ollama",  # Ollama doesn't need a real key
        )
        self.model = model
        self.max_turns = max_turns
        self.verbose = verbose

        self._bridge = SketchUpWSClient(host=host, port=port, timeout=30)
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def _ensure_bridge(self) -> None:
        if not self._bridge.is_connected:
            self._bridge.connect()
            if self.verbose:
                print("[bridge] Connected to SketchUp")

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        method = _TOOL_TO_METHOD.get(tool_name)
        if not method:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        self._ensure_bridge()

        try:
            if method.startswith("local."):
                if method == "local.parse_dxf_plan":
                    from su_mcp_bridge.parser.dxf import parse_dxf_walls

                    walls = parse_dxf_walls(
                        filepath=tool_input["filepath"],
                        layer_name=tool_input.get("layer_name"),
                        default_thickness_mm=tool_input.get("default_thickness_mm", 200.0),
                        default_height_mm=tool_input.get("default_height_mm", 2500.0),
                        scale_factor=tool_input.get("scale_factor", 1.0),
                    )
                    return json.dumps(
                        {"status": "parsed", "wall_count": len(walls), "walls": walls}, indent=2
                    )
                return json.dumps({"error": f"Unknown local method {method}"})

            result = self._bridge.send_request(method, tool_input)
            return json.dumps(result, indent=2)
        except BridgeConnectionError as e:
            return json.dumps({"error": f"Bridge connection failed: {e}"})
        except BridgeTimeout as e:
            return json.dumps({"error": f"Bridge timeout: {e}"})
        except BridgeError as e:
            return json.dumps({"error": str(e), "code": e.code})
        except Exception as e:
            return json.dumps({"error": f"Tool execution failed: {e}"})

    def chat(self, user_message: str) -> str:
        """Run a full agentic conversation from a single user message."""
        self.messages.append({"role": "user", "content": user_message})

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"  User: {user_message[:80]}{'...' if len(user_message) > 80 else ''}")
            print(f"{'=' * 60}")

        final_text = ""

        for _turn in range(self.max_turns):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=TOOLS,
                    temperature=0.1,
                )
            except Exception as e:
                error_msg = f"[error] LLM call failed: {e}"
                if self.verbose:
                    print(error_msg)
                return error_msg

            choice = response.choices[0]
            msg = choice.message

            # No tool calls — final response
            if not msg.tool_calls:
                final_text = msg.content or ""
                self.messages.append({"role": "assistant", "content": final_text})
                if self.verbose:
                    print(
                        f"\n[assistant] {final_text[:300]}{'...' if len(final_text) > 300 else ''}"
                    )
                break

            # Process tool calls
            self.messages.append(msg.model_dump())

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {}

                if self.verbose:
                    args_preview = json.dumps(tool_input, separators=(",", ":"))
                    if len(args_preview) > 80:
                        args_preview = args_preview[:77] + "..."
                    print(f"  [tool] {tool_name}({args_preview})")

                result_str = self._execute_tool(tool_name, tool_input)

                if self.verbose:
                    preview = result_str[:120] + "..." if len(result_str) > 120 else result_str
                    print(f"         -> {preview}")

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    }
                )

            # Check if we also had text content alongside tool calls
            if msg.content and self.verbose:
                print(f"  [thinking] {msg.content[:100]}")
        else:
            if self.verbose:
                print(f"  [warning] Hit max_turns ({self.max_turns})")

        return final_text

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def disconnect(self) -> None:
        self._bridge.disconnect()
