"""
tools/registry.py — Tool Registry for AI Surfaces
====================================================
Maps tool names to their implementations for MCP/API/Antigravity integration.
"""
from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass, field


@dataclass
class ToolDef:
    """Definition of a single tool."""
    name: str
    description: str
    method: str  # JSON-RPC method name
    params_schema: Dict[str, Any] = field(default_factory=dict)
    requires_batch: bool = False


# Master registry of all available tools
TOOLS: list[ToolDef] = [
    # --- Wall Operations ---
    ToolDef(
        name="create_wall",
        description="Create a wall from centerline start/end points with given thickness and height.",
        method="ops.wall.create",
        params_schema={
            "ai_id": {"type": "string", "required": True},
            "start_x": {"type": "number", "required": True, "unit": "inches"},
            "start_y": {"type": "number", "required": True, "unit": "inches"},
            "end_x": {"type": "number", "required": True, "unit": "inches"},
            "end_y": {"type": "number", "required": True, "unit": "inches"},
            "thickness": {"type": "number", "default": 5.91, "unit": "inches"},
            "height": {"type": "number", "default": 110.24, "unit": "inches"},
            "level": {"type": "string", "default": "GF"},
        }
    ),
    # --- Opening Operations ---
    ToolDef(
        name="cut_opening",
        description="Cut a door or window opening in an existing wall using boolean subtraction.",
        method="ops.opening.cut",
        params_schema={
            "ai_id": {"type": "string", "required": True},
            "wall_id": {"type": "string", "required": True},
            "offset": {"type": "number", "required": True, "unit": "inches"},
            "width": {"type": "number", "required": True, "unit": "inches"},
            "height": {"type": "number", "required": True, "unit": "inches"},
            "sill": {"type": "number", "default": 0, "unit": "inches"},
        }
    ),
    # --- Slab Operations ---
    ToolDef(
        name="create_slab",
        description="Create a floor or ceiling slab from a polygon outline.",
        method="ops.slab.create",
        params_schema={
            "ai_id": {"type": "string", "required": True},
            "polygon": {"type": "array", "required": True, "unit": "mm"},
            "thickness_mm": {"type": "number", "default": 150},
            "top_or_bottom": {"type": "string", "default": "top"},
            "base_z_mm": {"type": "number", "default": 0},
        }
    ),
    # --- Primitive Operations ---
    ToolDef(
        name="create_primitive",
        description="Create a geometric primitive (box, cylinder, sphere, cone, pyramid).",
        method="ops.primitive.create",
        params_schema={
            "ai_id": {"type": "string", "required": True},
            "kind": {"type": "string", "required": True, "enum": ["box", "cylinder", "sphere", "cone", "pyramid"]},
            "dimensions": {"type": "object", "required": True},
            "transform": {"type": "object", "default": {}},
        }
    ),
    # --- Batch ---
    ToolDef(
        name="batch_operations",
        description="Execute multiple operations atomically in a single SketchUp undo step.",
        method="ops.batch",
        params_schema={
            "ops": {"type": "array", "required": True},
        }
    ),
    # --- Delete ---
    ToolDef(
        name="delete_entity",
        description="Delete an entity by its ai_id.",
        method="ops.delete",
        params_schema={
            "ai_id": {"type": "string", "required": True},
        }
    ),
    # --- Material ---
    ToolDef(
        name="set_material",
        description="Apply a color material to an entity.",
        method="ops.set_material",
        params_schema={
            "ai_id": {"type": "string", "required": True},
            "color_hex": {"type": "string", "required": True},
        }
    ),
    # --- Dimension ---
    ToolDef(
        name="create_dimension",
        description="Add a linear dimension to the model.",
        method="ops.dimension.create",
        params_schema={
            "ai_id": {"type": "string", "required": True},
            "start_pt": {"type": "array", "required": True, "unit": "inches"},
            "end_pt": {"type": "array", "required": True, "unit": "inches"},
            "offset_vector": {"type": "array", "default": [0,0,10], "unit": "inches"},
        }
    ),
    # --- View Capture ---
    ToolDef(
        name="capture_view",
        description="Capture a screenshot of the model from a preset camera angle.",
        method="view.capture",
        params_schema={
            "preset": {"type": "string", "required": True, "enum": ["iso", "plan", "elev_s", "elev_n", "elev_e", "elev_w"]},
            "width": {"type": "integer", "default": 1920},
            "height": {"type": "integer", "default": 1080},
        }
    ),
    # --- Clear Model ---
    ToolDef(
        name="clear_model",
        description="Delete all entities from the active model.",
        method="ops.clear_model",
    ),
    # --- Query ---
    ToolDef(
        name="export_model_json",
        description="Export the current model state as a JSON summary of all AI-tracked entities.",
        method="query.export_json",
    ),
    ToolDef(
        name="verify_model",
        description="Verify that all expected ai_ids exist in the model. Reports divergences.",
        method="query.verify",
        params_schema={
            "expected_ids": {"type": "array", "required": True},
        }
    ),
    # --- Ping ---
    ToolDef(
        name="ping",
        description="Test connectivity to the SketchUp bridge.",
        method="ping",
    ),
]


def get_tool(name: str) -> Optional[ToolDef]:
    """Look up a tool by name."""
    for tool in TOOLS:
        if tool.name == name:
            return tool
    return None


def list_tools() -> list[str]:
    """Return all registered tool names."""
    return [t.name for t in TOOLS]


def tool_count() -> int:
    """Total number of registered tools."""
    return len(TOOLS)
