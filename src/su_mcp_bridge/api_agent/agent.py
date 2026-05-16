"""
api_agent/agent.py — Standalone Anthropic-powered agent for SketchUp
====================================================================

A synchronous agentic loop that talks to Claude via the Anthropic SDK,
providing all SketchUp bridge operations as tool-use functions.

Usage:
    from su_mcp_bridge.api_agent.agent import BuilderAgent
    agent = BuilderAgent()
    agent.chat("Build a 6×7m house with 4 walls, slab, door, window, and gable roof")

Or via CLI:
    python -m su_mcp_bridge.cli.sb agent "Build a house"
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import anthropic

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
# Tool definitions (Anthropic format)
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    # -- System --
    {
        "name": "ping",
        "description": "Test connectivity to the SketchUp bridge.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "hello",
        "description": "Handshake with the bridge. Returns plugin version and capabilities.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # -- Walls --
    {
        "name": "create_wall",
        "description": "Create a wall from two centerline points. All dimensions in mm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ai_id": {"type": "string", "description": "Unique wall ID, e.g. 'W1'"},
                "centerline": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                    "description": "Two points [[x1,y1],[x2,y2]] in mm",
                },
                "thickness_mm": {"type": "number", "default": 150},
                "height_mm": {"type": "number", "default": 2800},
                "level": {"type": "string", "default": "GF"},
            },
            "required": ["ai_id", "centerline"],
        },
    },
    {
        "name": "modify_wall",
        "description": "Modify an existing wall (delete + recreate). Re-cut openings afterwards.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ai_id": {"type": "string"},
                "centerline": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "thickness_mm": {"type": "number", "default": 150},
                "height_mm": {"type": "number", "default": 2800},
                "level": {"type": "string", "default": "GF"},
            },
            "required": ["ai_id", "centerline"],
        },
    },
    {
        "name": "delete_wall",
        "description": "Delete a wall by ai_id.",
        "input_schema": {
            "type": "object",
            "properties": {"ai_id": {"type": "string"}},
            "required": ["ai_id"],
        },
    },
    # -- Openings --
    {
        "name": "cut_opening",
        "description": "Cut a door/window opening in a wall. sill_mm=0 for doors, ~900 for windows.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ai_id": {"type": "string", "description": "Opening ID, e.g. 'DOOR_1'"},
                "wall_id": {"type": "string", "description": "ID of the wall to cut"},
                "offset_mm": {
                    "type": "number",
                    "description": "Distance from wall start along centerline",
                },
                "width_mm": {"type": "number"},
                "height_mm": {"type": "number"},
                "sill_mm": {"type": "number", "default": 0},
            },
            "required": ["ai_id", "wall_id", "offset_mm", "width_mm", "height_mm"],
        },
    },
    {
        "name": "modify_opening",
        "description": "Modify an opening. Rebuilds the wall with updated params.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ai_id": {"type": "string"},
                "wall_id": {"type": "string"},
                "offset_mm": {"type": "number"},
                "width_mm": {"type": "number"},
                "height_mm": {"type": "number"},
                "sill_mm": {"type": "number"},
            },
            "required": ["ai_id"],
        },
    },
    {
        "name": "delete_opening",
        "description": "Delete an opening. Rebuilds the wall without it.",
        "input_schema": {
            "type": "object",
            "properties": {"ai_id": {"type": "string"}, "wall_id": {"type": "string"}},
            "required": ["ai_id"],
        },
    },
    # -- Slabs --
    {
        "name": "create_slab",
        "description": "Create a floor/ceiling slab from polygon outline in mm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ai_id": {"type": "string"},
                "polygon": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "thickness_mm": {"type": "number", "default": 150},
                "top_or_bottom": {"type": "string", "enum": ["top", "bottom"], "default": "bottom"},
                "base_z_mm": {"type": "number", "default": 0},
            },
            "required": ["ai_id", "polygon"],
        },
    },
    # -- Roofs --
    {
        "name": "create_roof",
        "description": "Create a roof from footprint polygon. Kinds: flat, shed, gable, hip.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ai_id": {"type": "string"},
                "footprint": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "kind": {
                    "type": "string",
                    "enum": ["flat", "shed", "gable", "hip"],
                    "default": "gable",
                },
                "pitch_deg": {"type": "number", "default": 30},
                "ridge_height_mm": {"type": "number", "default": 0},
                "base_z_mm": {"type": "number", "default": 0},
            },
            "required": ["ai_id", "footprint"],
        },
    },
    {
        "name": "delete_roof",
        "description": "Delete a roof by ai_id.",
        "input_schema": {
            "type": "object",
            "properties": {"ai_id": {"type": "string"}},
            "required": ["ai_id"],
        },
    },
    # -- Components --
    {
        "name": "place_component",
        "description": "Place a component (recipe: 'door'/'window', or .skp path).",
        "input_schema": {
            "type": "object",
            "properties": {
                "ai_id": {"type": "string"},
                "position_mm": {"type": "array", "items": {"type": "number"}},
                "recipe": {"type": "string"},
                "definition_path": {"type": "string"},
                "rotation_deg": {"type": "number", "default": 0},
                "width_mm": {"type": "number", "default": 900},
                "height_mm": {"type": "number", "default": 2100},
                "thickness_mm": {"type": "number", "default": 40},
                "attached_to": {"type": "string"},
            },
            "required": ["ai_id", "position_mm"],
        },
    },
    {
        "name": "delete_component",
        "description": "Delete a component by ai_id.",
        "input_schema": {
            "type": "object",
            "properties": {"ai_id": {"type": "string"}},
            "required": ["ai_id"],
        },
    },
    # -- Materials & Layers --
    {
        "name": "upsert_material",
        "description": "Create/update a material. color_hex is 'RRGGBB' without #.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "color_hex": {"type": "string"},
                "alpha": {"type": "number", "default": 1.0},
            },
            "required": ["id", "color_hex"],
        },
    },
    {
        "name": "assign_material",
        "description": "Assign a material to multiple entities.",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_id": {"type": "string"},
                "target_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["material_id", "target_ids"],
        },
    },
    # -- Batch & Lifecycle --
    {
        "name": "batch_operations",
        "description": "Execute multiple ops atomically. Each item: {method, params}.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ops": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["ops"],
        },
    },
    {
        "name": "clear_model",
        "description": "Delete all entities and reset the ai_id cache.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "delete_entity",
        "description": "Delete any entity by ai_id.",
        "input_schema": {
            "type": "object",
            "properties": {"ai_id": {"type": "string"}},
            "required": ["ai_id"],
        },
    },
    # -- Queries --
    {
        "name": "scene_summary",
        "description": "Token-efficient model digest (~200 tokens). Call this first.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "inspect_entity",
        "description": "Full attributes of a single entity.",
        "input_schema": {
            "type": "object",
            "properties": {"ai_id": {"type": "string"}},
            "required": ["ai_id"],
        },
    },
    {
        "name": "export_model_json",
        "description": "Full model state dump. Expensive — use sparingly.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "verify_model",
        "description": "Check that all expected ai_ids exist in the model.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expected_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["expected_ids"],
        },
    },
    # -- Capture --
    {
        "name": "capture_view",
        "description": "Screenshot from a preset camera angle. Presets: plan, iso, elev_n/e/s/w.",
        "input_schema": {
            "type": "object",
            "properties": {
                "preset": {
                    "type": "string",
                    "enum": ["plan", "iso", "elev_n", "elev_e", "elev_s", "elev_w"],
                },
                "resolution": {"type": "string", "enum": ["low", "med", "high"], "default": "med"},
                "save_dir": {"type": "string"},
            },
            "required": ["preset"],
        },
    },
    {
        "name": "capture_canonical",
        "description": "Capture all 6 canonical views in one call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "resolution": {"type": "string", "default": "med"},
                "save_dir": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "parse_dxf_plan",
        "description": "Parse a DXF file to extract wall centerlines for batch creation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "layer_name": {"type": "string"},
                "default_thickness_mm": {"type": "number", "default": 200},
                "default_height_mm": {"type": "number", "default": 2500},
                "scale_factor": {"type": "number", "default": 1.0},
            },
            "required": ["filepath"],
        },
    },
    # -- v3.0 tools --
    {
        "name": "deep_scan",
        "description": "Comprehensive model scan. Returns all entities with type, layer, material, bounds, volume, solid status.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "detect_clashes",
        "description": "Detect geometric clashes (AABB overlaps) between tracked entities.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tolerance_mm": {"type": "number", "default": 1.0},
            },
            "required": [],
        },
    },
    {
        "name": "save_file",
        "description": "Save the active SketchUp model.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Optional save path"},
            },
            "required": [],
        },
    },
    {
        "name": "model_info",
        "description": "Get model metadata: path, units, entity count, definitions, materials, layers.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "generate_walkthrough",
        "description": "Generate an automated camera walkthrough video. Presets: orbit, flythrough, cinematic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "preset": {
                    "type": "string",
                    "enum": ["orbit", "flythrough", "cinematic"],
                    "default": "orbit",
                },
                "frames": {"type": "integer", "default": 120},
                "fps": {"type": "integer", "default": 30},
                "resolution": {"type": "string", "enum": ["low", "med", "high"], "default": "med"},
            },
            "required": [],
        },
    },
]

# Map tool names -> JSON-RPC method names
_TOOL_TO_METHOD: dict[str, str] = {
    "ping": "ping",
    "hello": "hello",
    "create_wall": "ops.wall.create",
    "modify_wall": "ops.wall.modify",
    "delete_wall": "ops.wall.delete",
    "cut_opening": "ops.opening.cut",
    "modify_opening": "ops.opening.modify",
    "delete_opening": "ops.opening.delete",
    "create_slab": "ops.slab.create",
    "create_roof": "ops.roof.create",
    "delete_roof": "ops.roof.delete",
    "place_component": "ops.component.place",
    "delete_component": "ops.component.delete",
    "upsert_material": "ops.material.upsert",
    "assign_material": "ops.material.assign",
    "batch_operations": "ops.batch",
    "clear_model": "ops.clear_model",
    "delete_entity": "ops.delete",
    "scene_summary": "query.scene_summary",
    "inspect_entity": "query.entity",
    "export_model_json": "query.export_json",
    "verify_model": "query.verify",
    "capture_view": "view.capture",
    "capture_canonical": "view.capture_canonical",
    "parse_dxf_plan": "local.parse_dxf_plan",
    "deep_scan": "query.deep_scan",
    "detect_clashes": "query.clash_detect",
    "save_file": "lifecycle.save",
    "model_info": "lifecycle.model_info",
    "generate_walkthrough": "view.walkthrough",
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert architectural modeler controlling SketchUp 2025.

## Rules
- All dimensions are in millimeters (mm).
- Entity IDs (ai_id) must be unique strings, e.g. W1, DOOR_FRONT, SLAB_GF.
- Use batch_operations for creating multiple walls/openings at once.
- Always call scene_summary first to understand the current model state.
- Always call verify_model after making changes to confirm zero divergences.
- Walls use centerline coordinates: [[x1,y1],[x2,y2]] in mm.
- Openings: sill_mm=0 for doors, 800-1200 for windows.
- offset_mm + width_mm must be <= wall length.
- sill_mm + height_mm must be <= wall height.
- Use butt joints: through walls extend by half-thickness of butting walls.
- Never create overlapping walls or openings that span T-junctions.

## Workflow
1. Read the user's request carefully
2. Call scene_summary to see what exists
3. Plan all entities with proper butt-joint calculations
4. Create walls (batch), then openings (batch), then slab/roof
5. Verify with verify_model
6. Capture views if requested

Be precise. Be deterministic. Think before you act.
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class BuilderAgent:
    """Synchronous tool-use agent loop powered by Anthropic Claude."""

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-20241022",
        api_key: str | None = None,
        host: str = "localhost",
        port: int = 9876,
        max_turns: int = 20,
        verbose: bool = True,
    ):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise OSError("ANTHROPIC_API_KEY not set. Export it or add to .env.")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_turns = max_turns
        self.verbose = verbose

        # SketchUp bridge
        self._bridge = SketchUpWSClient(host=host, port=port, timeout=30)

        # Conversation history
        self.messages: list[dict[str, Any]] = []

    def _ensure_bridge(self) -> None:
        if not self._bridge.is_connected:
            self._bridge.connect()
            if self.verbose:
                print("[bridge] Connected to SketchUp")

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call against the SketchUp bridge."""
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
        """Run a full agentic conversation from a single user message.

        Returns the final text response from Claude.
        """
        self.messages.append({"role": "user", "content": user_message})

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"  User: {user_message[:80]}{'...' if len(user_message) > 80 else ''}")
            print(f"{'=' * 60}")

        final_text = ""

        for _turn in range(self.max_turns):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.messages,
            )

            # Check stop reason
            if response.stop_reason == "end_turn":
                # Extract final text
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text += block.text
                self.messages.append({"role": "assistant", "content": response.content})
                if self.verbose:
                    print(
                        f"\n[assistant] {final_text[:200]}{'...' if len(final_text) > 200 else ''}"
                    )
                break

            elif response.stop_reason == "tool_use":
                # Process tool calls
                self.messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        if self.verbose:
                            input_preview = json.dumps(block.input, separators=(",", ":"))
                            if len(input_preview) > 80:
                                input_preview = input_preview[:77] + "..."
                            print(f"  [tool] {block.name}({input_preview})")

                        result_str = self._execute_tool(block.name, block.input)

                        if self.verbose:
                            result_preview = result_str
                            if len(result_preview) > 120:
                                result_preview = result_preview[:117] + "..."
                            print(f"         -> {result_preview}")

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_str,
                            }
                        )
                    elif hasattr(block, "text") and block.text:
                        if self.verbose:
                            print(f"  [thinking] {block.text[:100]}")

                self.messages.append({"role": "user", "content": tool_results})

            else:
                # Unknown stop reason
                if self.verbose:
                    print(f"  [stop] Unexpected stop_reason: {response.stop_reason}")
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text += block.text
                break
        else:
            if self.verbose:
                print(f"  [warning] Hit max_turns ({self.max_turns})")

        return final_text

    def reset(self) -> None:
        """Clear conversation history."""
        self.messages.clear()

    def disconnect(self) -> None:
        """Close the bridge connection."""
        self._bridge.disconnect()
