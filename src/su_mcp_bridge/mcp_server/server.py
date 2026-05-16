"""
mcp_server/server.py — MCP Server for the SU MCP Bridge
=============================================================

Exposes the SketchUp bridge operations as MCP tools that can be consumed
by Claude Desktop, Claude Code, and Antigravity.

Usage (stdio, for Claude Desktop / Claude Code):
    python -m su_mcp_bridge.mcp_server.server

Configuration in claude_desktop_config.json:
    {
      "mcpServers": {
        "sketchup": {
          "command": "python",
          "args": ["-m", "su_mcp_bridge.mcp_server.server"]
        }
      }
    }
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import base64

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image as MCPImage

# Ensure src/ is importable when run as a script.
_src = os.path.join(os.path.dirname(__file__), "..", "..")
if _src not in sys.path:
    sys.path.insert(0, os.path.abspath(_src))

from su_mcp_bridge.transport.ws_client import (
    SketchUpWSClient,
    BridgeError,
    BridgeTimeout,
    BridgeConnectionError,
)
from su_mcp_bridge.core.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# MCP Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "SAIE — SketchUp Automation & Intelligence Engine",
    instructions=(
        "Control SketchUp 2025 for architectural modeling. "
        "Create/modify/delete walls, openings, slabs, roofs, components, "
        "materials, and primitives. Capture views and query model state. "
        "Read/write BIM metadata attributes on any entity. "
        "All dimensions are in millimeters. Entity IDs are stable strings."
    ),
)

# ---------------------------------------------------------------------------
# Shared bridge client — lazy-connected singleton
# ---------------------------------------------------------------------------

_client: SketchUpWSClient | None = None


def _get_client() -> SketchUpWSClient:
    """Return the shared bridge client, connecting on first use."""
    global _client
    if _client is None:
        host = os.environ.get("SKETCHUP_HOST", "localhost")
        port = int(os.environ.get("SKETCHUP_PORT", "9876"))
        _client = SketchUpWSClient(host=host, port=port, timeout=30)
    if not _client.is_connected:
        _client.connect()
    return _client


def _call(method: str, params: dict | None = None, timeout: float | None = None) -> Any:
    """Send a JSON-RPC request to the SketchUp bridge and return the result."""
    from su_mcp_bridge.transport.ws_client import SketchUpWSClient
    client = _get_client()
    # Auto-scale timeout for batch calls based on the number of sub-ops.
    if timeout is None and method == "ops.batch":
        n_ops = len((params or {}).get("ops", []))
        timeout = SketchUpWSClient.batch_timeout(n_ops)
    try:
        return client.send_request(method, params or {}, timeout=timeout)
    except BridgeConnectionError as e:
        return {"error": f"Cannot connect to SketchUp: {e}"}
    except BridgeTimeout as e:
        return {"error": f"SketchUp did not respond in time: {e}"}
    except BridgeError as e:
        return {"error": str(e), "code": e.code}


# ===========================================================================
# SYSTEM TOOLS
# ===========================================================================


@mcp.tool()
def ping() -> str:
    """Test connectivity to the SketchUp bridge. Returns pong if alive."""
    result = _call("ping")
    return json.dumps(result, indent=2)


@mcp.tool()
def hello() -> str:
    """Handshake with the SketchUp bridge. Returns plugin version and capabilities."""
    result = _call("hello", {"client_version": "1.0.0"})
    return json.dumps(result, indent=2)

@mcp.tool()
def capture_view(
    preset: str = "iso",
    resolution: str = "med",
    style: str = "default",
    entity_id: str | None = None,
    ai_id: str | None = None,
    name: str | None = None,
    isolate: bool = False,
) -> str:
    """Capture a screenshot of the SketchUp view. Optionally target a specific component.

    Args:
        preset: Camera preset: "plan", "iso", "elev_n", "elev_s", "elev_e", "elev_w" (default: "iso")
        resolution: "low", "med", "high", "ultra" (default: "med")
        style: Rendering style: "default", "hidden_line", "wireframe", "shaded", "shaded_tex", "monochrome", "xray"
        entity_id: Persistent ID of a specific component to focus on.
        ai_id: Custom AI ID of a specific component to focus on.
        name: Name of a specific component to focus on.
        isolate: If True, temporarily hides all other entities in the model to capture only the target.
    """
    params = {
        "preset": preset,
        "resolution": resolution,
        "style": style,
        "isolate": isolate,
    }
    if entity_id: params["entity_id"] = entity_id
    if ai_id: params["ai_id"] = ai_id
    if name: params["name"] = name

    result = _call("view.capture", params)
    return json.dumps(result, indent=2)


# ===========================================================================
# WALL TOOLS
# ===========================================================================


@mcp.tool()
def create_wall(
    ai_id: str,
    centerline: list[list[float]],
    thickness_mm: float = 150,
    height_mm: float = 2800,
    level: str = "GF",
) -> str:
    """Create a wall from two centerline points.

    Args:
        ai_id: Unique identifier for this wall (e.g. "W1", "W_SOUTH")
        centerline: Two points [[x1,y1],[x2,y2]] in millimeters
        thickness_mm: Wall thickness in mm (default 150)
        height_mm: Wall height in mm (default 2800)
        level: Level/layer name (default "GF")
    """
    result = _call("ops.wall.create", {
        "ai_id": ai_id,
        "centerline": centerline,
        "thickness_mm": thickness_mm,
        "height_mm": height_mm,
        "level": level,
    })
    return json.dumps(result, indent=2)


@mcp.tool()
def modify_wall(
    ai_id: str,
    centerline: list[list[float]],
    thickness_mm: float = 150,
    height_mm: float = 2800,
    level: str = "GF",
) -> str:
    """Modify an existing wall (delete + recreate). Re-cut openings after calling this.

    Args:
        ai_id: ID of the wall to modify
        centerline: New centerline [[x1,y1],[x2,y2]] in mm
        thickness_mm: New thickness in mm
        height_mm: New height in mm
        level: Level/layer name
    """
    result = _call("ops.wall.modify", {
        "ai_id": ai_id,
        "centerline": centerline,
        "thickness_mm": thickness_mm,
        "height_mm": height_mm,
        "level": level,
    })
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_wall(ai_id: str) -> str:
    """Delete a wall by its ai_id.

    Args:
        ai_id: ID of the wall to delete
    """
    result = _call("ops.wall.delete", {"ai_id": ai_id})
    return json.dumps(result, indent=2)


# ===========================================================================
# OPENING TOOLS
# ===========================================================================


@mcp.tool()
def cut_opening(
    ai_id: str,
    wall_id: str,
    offset_mm: float,
    width_mm: float,
    height_mm: float,
    sill_mm: float = 0,
) -> str:
    """Cut a door or window opening in an existing wall using boolean subtraction.

    Args:
        ai_id: Unique identifier for this opening (e.g. "DOOR_1")
        wall_id: ai_id of the wall to cut
        offset_mm: Distance from wall start along centerline (mm)
        width_mm: Opening width in mm
        height_mm: Opening height in mm
        sill_mm: Height above floor in mm (0 for doors, ~900 for windows)
    """
    result = _call("ops.opening.cut", {
        "ai_id": ai_id,
        "wall_id": wall_id,
        "offset_mm": offset_mm,
        "width_mm": width_mm,
        "height_mm": height_mm,
        "sill_mm": sill_mm,
    })
    return json.dumps(result, indent=2)


@mcp.tool()
def modify_opening(
    ai_id: str,
    wall_id: str = "",
    offset_mm: float = 0,
    width_mm: float = 0,
    height_mm: float = 0,
    sill_mm: float = 0,
) -> str:
    """Modify an existing opening. Rebuilds the wall with updated opening params.

    Args:
        ai_id: ID of the opening to modify
        wall_id: Wall containing the opening (auto-detected if empty)
        offset_mm: New offset from wall start (mm)
        width_mm: New width (mm)
        height_mm: New height (mm)
        sill_mm: New sill height (mm)
    """
    params: dict[str, Any] = {"ai_id": ai_id}
    if wall_id:
        params["wall_id"] = wall_id
    if offset_mm:
        params["offset_mm"] = offset_mm
    if width_mm:
        params["width_mm"] = width_mm
    if height_mm:
        params["height_mm"] = height_mm
    if sill_mm:
        params["sill_mm"] = sill_mm
    result = _call("ops.opening.modify", params)
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_opening(ai_id: str, wall_id: str = "") -> str:
    """Delete an opening. Rebuilds the wall without this opening.

    Args:
        ai_id: ID of the opening to delete
        wall_id: Wall containing the opening (auto-detected if empty)
    """
    params: dict[str, Any] = {"ai_id": ai_id}
    if wall_id:
        params["wall_id"] = wall_id
    result = _call("ops.opening.delete", params)
    return json.dumps(result, indent=2)


# ===========================================================================
# SLAB TOOLS
# ===========================================================================


@mcp.tool()
def create_slab(
    ai_id: str,
    polygon: list[list[float]],
    thickness_mm: float = 150,
    top_or_bottom: str = "bottom",
    base_z_mm: float = 0,
) -> str:
    """Create a floor or ceiling slab from a polygon outline.

    Args:
        ai_id: Unique identifier (e.g. "SLAB_GF")
        polygon: CCW outline points [[x,y],...] in mm, at least 3 points
        thickness_mm: Slab thickness (default 150)
        top_or_bottom: "top" or "bottom" relative to base_z
        base_z_mm: Base elevation in mm
    """
    result = _call("ops.slab.create", {
        "ai_id": ai_id,
        "polygon": polygon,
        "thickness_mm": thickness_mm,
        "top_or_bottom": top_or_bottom,
        "base_z_mm": base_z_mm,
    })
    return json.dumps(result, indent=2)


# ===========================================================================
# ROOF TOOLS
# ===========================================================================


@mcp.tool()
def create_roof(
    ai_id: str,
    footprint: list[list[float]],
    kind: str = "gable",
    pitch_deg: float = 30,
    ridge_height_mm: float = 0,
    eave_overhang_mm: float = 0,
    base_z_mm: float = 0,
) -> str:
    """Create a roof from a footprint polygon.

    Args:
        ai_id: Unique identifier (e.g. "ROOF_1")
        footprint: Polygon points [[x,y],...] in mm
        kind: "flat", "shed", "gable", or "hip"
        pitch_deg: Roof pitch in degrees (default 30)
        ridge_height_mm: Manual ridge height (0 = auto from pitch)
        eave_overhang_mm: Overhang beyond footprint
        base_z_mm: Base elevation (typically wall top)
    """
    result = _call("ops.roof.create", {
        "ai_id": ai_id,
        "kind": kind,
        "footprint": footprint,
        "pitch_deg": pitch_deg,
        "ridge_height_mm": ridge_height_mm,
        "eave_overhang_mm": eave_overhang_mm,
        "base_z_mm": base_z_mm,
    })
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_roof(ai_id: str) -> str:
    """Delete a roof by its ai_id.

    Args:
        ai_id: ID of the roof to delete
    """
    result = _call("ops.roof.delete", {"ai_id": ai_id})
    return json.dumps(result, indent=2)


# ===========================================================================
# COMPONENT TOOLS
# ===========================================================================


@mcp.tool()
def place_component(
    ai_id: str,
    position_mm: list[float],
    recipe: str = "",
    definition_path: str = "",
    rotation_deg: float = 0,
    width_mm: float = 900,
    height_mm: float = 2100,
    thickness_mm: float = 40,
    attached_to: str = "",
) -> str:
    """Place a component (door, window, or .skp file).

    Args:
        ai_id: Unique identifier
        position_mm: Insertion point [x,y,z] in mm
        recipe: "door" or "window" for built-in geometry
        definition_path: Path to .skp file (alternative to recipe)
        rotation_deg: Rotation around Z axis
        width_mm: Width for recipe components
        height_mm: Height for recipe components
        thickness_mm: Thickness for recipe components
        attached_to: Opening ai_id to snap to
    """
    params: dict[str, Any] = {
        "ai_id": ai_id,
        "position_mm": position_mm,
        "rotation_deg": rotation_deg,
        "width_mm": width_mm,
        "height_mm": height_mm,
        "thickness_mm": thickness_mm,
    }
    if recipe:
        params["recipe"] = recipe
    if definition_path:
        params["definition_path"] = definition_path
    if attached_to:
        params["attached_to"] = attached_to
    result = _call("ops.component.place", params)
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_component(ai_id: str) -> str:
    """Delete a component by its ai_id.

    Args:
        ai_id: ID of the component to delete
    """
    result = _call("ops.component.delete", {"ai_id": ai_id})
    return json.dumps(result, indent=2)


# ===========================================================================
# PRIMITIVE TOOLS
# ===========================================================================


@mcp.tool()
def create_primitive(
    ai_id: str,
    kind: str,
    dimensions: dict,
    position_mm: list[float] | None = None,
    rotation_deg: list[float] | None = None,
) -> str:
    """Create a geometric primitive (box, sphere, cylinder, cone, pyramid).

    Args:
        ai_id: Unique identifier
        kind: "box", "sphere", "cylinder", "cone", or "pyramid"
        dimensions: Kind-specific dims, e.g. {"width_mm":1000, "depth_mm":500, "height_mm":800}
        position_mm: Position [x,y,z] in mm (default origin)
        rotation_deg: Rotation [rx,ry,rz] in degrees (default [0,0,0])
    """
    transform: dict[str, Any] = {}
    if position_mm:
        transform["position_mm"] = position_mm
    if rotation_deg:
        transform["rotation_deg"] = rotation_deg
    result = _call("ops.primitive.create", {
        "ai_id": ai_id,
        "kind": kind,
        "dimensions": dimensions,
        "transform": transform,
    })
    return json.dumps(result, indent=2)


# ===========================================================================
# MATERIAL & LAYER TOOLS
# ===========================================================================


@mcp.tool()
def upsert_material(
    id: str,
    color_hex: str,
    alpha: float = 1.0,
) -> str:
    """Create or update a material.

    Args:
        id: Material identifier (e.g. "MAT_BRICK")
        color_hex: Color as "RRGGBB" hex string (no # prefix)
        alpha: Opacity 0.0-1.0 (default 1.0)
    """
    result = _call("ops.material.upsert", {
        "id": id,
        "color_hex": color_hex,
        "alpha": alpha,
    })
    return json.dumps(result, indent=2)


@mcp.tool()
def assign_material(material_id: str, target_ids: list[str]) -> str:
    """Assign a material to multiple entities.

    Args:
        material_id: ID of the material to assign
        target_ids: List of entity ai_ids to apply the material to
    """
    result = _call("ops.material.assign", {
        "material_id": material_id,
        "target_ids": target_ids,
    })
    return json.dumps(result, indent=2)


@mcp.tool()
def upsert_layer(
    id: str,
    color: list[int] | None = None,
    visible: bool = True,
) -> str:
    """Create or update a layer (tag).

    Args:
        id: Layer name/identifier
        color: Optional RGB color [r,g,b] 0-255
        visible: Whether the layer is visible (default True)
    """
    params: dict[str, Any] = {"id": id, "visible": visible}
    if color:
        params["color"] = color
    result = _call("ops.layer.upsert", params)
    return json.dumps(result, indent=2)


@mcp.tool()
def assign_layer(layer_id: str, target_ids: list[str]) -> str:
    """Assign entities to a layer.

    Args:
        layer_id: ID of the layer
        target_ids: List of entity ai_ids to assign
    """
    result = _call("ops.layer.assign", {
        "layer_id": layer_id,
        "target_ids": target_ids,
    })
    return json.dumps(result, indent=2)


# ===========================================================================
# BATCH & LIFECYCLE
# ===========================================================================


@mcp.tool()
def batch_operations(ops: list[dict]) -> str:
    """Execute multiple operations atomically in a single SketchUp undo step.

    Args:
        ops: List of operations, each with "method" and "params" keys.
             Example: [{"method": "ops.wall.create", "params": {...}}, ...]
    """
    result = _call("ops.batch", {"ops": ops})
    return json.dumps(result, indent=2)


@mcp.tool()
def clear_model() -> str:
    """Delete all entities from the active SketchUp model and reset the ai_id cache."""
    result = _call("ops.clear_model")
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_entity(ai_id: str) -> str:
    """Delete any entity by its ai_id.

    Args:
        ai_id: ID of the entity to delete
    """
    result = _call("ops.delete", {"ai_id": ai_id})
    return json.dumps(result, indent=2)


# ===========================================================================
# QUERY TOOLS
# ===========================================================================


@mcp.tool()
def scene_summary() -> str:
    """Get a token-efficient summary of the model (~200 tokens).
    Returns entity counts, layers, materials, and bounds.
    Always call this first after connecting."""
    result = _call("query.scene_summary")
    return json.dumps(result, indent=2)


@mcp.tool()
def inspect_entity(ai_id: str) -> str:
    """Get full attributes of a single entity by ai_id.

    Args:
        ai_id: ID of the entity to inspect
    """
    result = _call("query.entity", {"ai_id": ai_id})
    return json.dumps(result, indent=2)


@mcp.tool()
def export_model_json() -> str:
    """Export the full model state as JSON. Expensive - use sparingly.
    Prefer scene_summary() or inspect_entity() for most queries."""
    result = _call("query.export_json")
    return json.dumps(result, indent=2)


@mcp.tool()
def verify_model(expected_ids: list[str]) -> str:
    """Verify that all expected ai_ids exist in the model.

    Args:
        expected_ids: List of ai_ids that should be present
    """
    result = _call("query.verify", {"expected_ids": expected_ids})
    return json.dumps(result, indent=2)


# ===========================================================================
# VIEW & CAPTURE TOOLS
# ===========================================================================


@mcp.tool()
def capture_view(
    preset: str = "iso",
    resolution: str = "med",
    save_dir: str = "",
) -> str:
    """Capture a screenshot of the model from a preset camera angle.

    Args:
        preset: Camera preset - "plan", "iso", "elev_n", "elev_e", "elev_s", "elev_w"
        resolution: "low" (512x384), "med" (1024x768), "high" (1920x1440)
        save_dir: Directory to save captures (default: C:/su_capture)
    """
    params: dict[str, Any] = {"preset": preset, "resolution": resolution}
    if save_dir:
        params["save_dir"] = save_dir
    else:
        try:
            from su_mcp_bridge.core.project import get_active_project
            project = get_active_project()
            if project:
                params["project_captures_dir"] = str(project.captures_dir)
        except Exception:
            pass
    result = _call("view.capture", params)
    return json.dumps(result, indent=2)


@mcp.tool()
def capture_canonical(
    resolution: str = "med",
    save_dir: str = "",
) -> str:
    """Capture all 6 canonical views (plan, iso, 4 elevations) in one call.

    Args:
        resolution: "low", "med" (default), or "high"
        save_dir: Directory to save captures
    """
    params: dict[str, Any] = {"resolution": resolution}
    if save_dir:
        params["save_dir"] = save_dir
    else:
        try:
            from su_mcp_bridge.core.project import get_active_project
            project = get_active_project()
            if project:
                params["project_captures_dir"] = str(project.captures_dir)
        except Exception:
            pass
    result = _call("view.capture_canonical", params)
    return json.dumps(result, indent=2)


# ===========================================================================
# LIVE VIEW TOOLS — inline snapshots for AI, MJPEG stream for human observer
# ===========================================================================


@mcp.tool()
def view_snapshot(
    width: int = 800,
    height: int = 600,
    quality: int = 70,
    source: str = "window",
):
    """Capture the SketchUp view as an inline JPEG image returned directly to the model.

    Use this when you want to SEE what's currently in the SketchUp viewport —
    for example to verify the result of an action, sanity-check a build step,
    or inspect the model state. The image is returned inline so you read it
    immediately, with no file path or disk roundtrip.

    Args:
        width: image width in pixels (default 800) — only honoured by source='view'
        height: image height in pixels (default 600) — only honoured by source='view'
        quality: JPEG quality 1-100 (default 70, lower = smaller payload)
        source: "window" (default) captures the actual SketchUp window via Win32
                PrintWindow, INCLUDING axes, selection highlights, gizmos, and
                tool overlays — what the user actually sees. Captured at the
                window's native resolution. "view" uses view.write_image() for a
                clean offline render at exactly the requested dimensions — no
                axes/selection/overlays, ideal for high-resolution AI inspection
                of geometry alone.
    """
    result = _call("view.snapshot", {
        "width": width,
        "height": height,
        "quality": quality,
        "source": source,
    })
    if isinstance(result, dict) and result.get("error"):
        return json.dumps(result, indent=2)
    if not isinstance(result, dict) or not result.get("image_base64"):
        return json.dumps({"error": "snapshot returned no image", "raw": result}, indent=2)
    img_bytes = base64.b64decode(result["image_base64"])
    return MCPImage(data=img_bytes, format="jpeg")


@mcp.tool()
def start_live_view(fps: int = 5) -> str:
    """Start the HTTP MJPEG live-view server so a human can watch SketchUp in a browser.

    Returns a URL the user can open in any browser to watch the SketchUp
    canvas in real time while the AI is working. Independent of the AI's
    snapshot tools — the human gets a continuously refreshing view; the AI
    keeps using view_snapshot for its own inspection.

    Args:
        fps: target frame rate (1-30, default 5). Higher values stall SketchUp
             more often because view.write_image is synchronous on the main
             thread. 3-8 fps is a sensible range.
    """
    result = _call("view.stream.start", {"fps": max(1, min(30, fps))})
    return json.dumps(result, indent=2)


@mcp.tool()
def stop_live_view() -> str:
    """Stop the HTTP MJPEG live-view server and disconnect any browser clients."""
    return json.dumps(_call("view.stream.stop"), indent=2)


@mcp.tool()
def live_view_status() -> str:
    """Report HTTP MJPEG live-view server status (running, port, URL, client count, last-frame age)."""
    return json.dumps(_call("view.stream.status"), indent=2)


@mcp.tool()
def configure_live_view(
    width: int | None = None,
    height: int | None = None,
    quality: int | None = None,
    cache_ms: int | None = None,
) -> str:
    """Configure the default capture dimensions and quality used by view_snapshot and the MJPEG stream.

    Args:
        width: default frame width in pixels
        height: default frame height in pixels
        quality: default JPEG quality 1-100
        cache_ms: minimum ms between captures — multiple consumers within
                  this window share a single capture (default 100)
    """
    params: dict[str, Any] = {}
    if width    is not None: params["width"]    = width
    if height   is not None: params["height"]   = height
    if quality  is not None: params["quality"]  = quality
    if cache_ms is not None: params["cache_ms"] = cache_ms
    return json.dumps(_call("view.stream.configure", params), indent=2)


# ===========================================================================
# VIEW CONTROL — orbit / zoom / pan / camera / selection / isolation
# ===========================================================================


@mcp.tool()
def orbit_view(horizontal: float = 0.0, vertical: float = 0.0) -> str:
    """Orbit the camera around its current target point.

    Args:
        horizontal: degrees around the world Z axis (positive = clockwise from above)
        vertical:   degrees up/down around the camera's right axis
    """
    return json.dumps(
        _call("view.orbit", {"horizontal": horizontal, "vertical": vertical}),
        indent=2,
    )


@mcp.tool()
def zoom_view(factor: float = 1.0) -> str:
    """Zoom the view by a multiplicative factor.

    Args:
        factor: <1.0 zooms in (e.g. 0.5 doubles apparent size),
                >1.0 zooms out (e.g. 2.0 halves apparent size)
    """
    return json.dumps(_call("view.zoom", {"factor": factor}), indent=2)


@mcp.tool()
def zoom_extents() -> str:
    """Zoom out to fit all visible entities in the viewport."""
    return json.dumps(_call("view.zoom_extents"), indent=2)


@mcp.tool()
def zoom_selection() -> str:
    """Zoom to fit the current selection in the viewport."""
    return json.dumps(_call("view.zoom_selection"), indent=2)


@mcp.tool()
def pan_view(dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> str:
    """Pan the camera by shifting eye + target by (dx, dy, dz) in world mm.

    Args:
        dx, dy, dz: world-space offset in millimetres
    """
    return json.dumps(_call("view.pan", {"dx": dx, "dy": dy, "dz": dz}), indent=2)


@mcp.tool()
def set_camera(
    eye: list[float] | None = None,
    target: list[float] | None = None,
    up: list[float] | None = None,
    perspective: bool | None = None,
    fov: float | None = None,
) -> str:
    """Set the camera directly. All args optional — omitted fields keep current values.

    Args:
        eye:    [x,y,z] camera position
        target: [x,y,z] look-at point
        up:     [x,y,z] up vector (default world Z)
        perspective: True for perspective, False for parallel projection
        fov:    field-of-view in degrees (perspective only)
    """
    params: dict[str, Any] = {}
    if eye         is not None: params["eye"]         = eye
    if target      is not None: params["target"]      = target
    if up          is not None: params["up"]          = up
    if perspective is not None: params["perspective"] = perspective
    if fov         is not None: params["fov"]         = fov
    return json.dumps(_call("view.set_camera", params), indent=2)


@mcp.tool()
def get_camera() -> str:
    """Read the current camera state (eye, target, up, perspective, fov)."""
    return json.dumps(_call("view.get_camera"), indent=2)


@mcp.tool()
def select_entity(
    ai_id: str | None = None,
    ai_ids: list[str] | None = None,
    persistent_id: str | None = None,
    persistent_ids: list[str] | None = None,
    name: str | None = None,
    mode: str = "add",
) -> str:
    """Add entities to the SketchUp selection (also highlights them in the view).

    Args:
        ai_id / ai_ids: one or many ai_id strings
        persistent_id / persistent_ids: one or many SketchUp persistent IDs
        name: entity name (used as a fallback lookup)
        mode: "add" (default), "replace" (clear first), or "toggle"
    """
    params: dict[str, Any] = {"mode": mode}
    if ai_id          is not None: params["ai_id"]          = ai_id
    if ai_ids         is not None: params["ai_ids"]         = ai_ids
    if persistent_id  is not None: params["persistent_id"]  = persistent_id
    if persistent_ids is not None: params["persistent_ids"] = persistent_ids
    if name           is not None: params["name"]           = name
    return json.dumps(_call("selection.select", params), indent=2)


@mcp.tool()
def deselect_entity(
    ai_id: str | None = None,
    ai_ids: list[str] | None = None,
    persistent_id: str | None = None,
    persistent_ids: list[str] | None = None,
) -> str:
    """Remove specified entities from the selection without clearing the rest."""
    params: dict[str, Any] = {}
    if ai_id          is not None: params["ai_id"]          = ai_id
    if ai_ids         is not None: params["ai_ids"]         = ai_ids
    if persistent_id  is not None: params["persistent_id"]  = persistent_id
    if persistent_ids is not None: params["persistent_ids"] = persistent_ids
    return json.dumps(_call("selection.deselect", params), indent=2)


@mcp.tool()
def clear_selection() -> str:
    """Clear the SketchUp selection (deselect everything)."""
    return json.dumps(_call("selection.clear"), indent=2)


@mcp.tool()
def get_selection() -> str:
    """Report what's currently selected — persistent_id, ai_id, type, name per item."""
    return json.dumps(_call("selection.info"), indent=2)


@mcp.tool()
def isolate_entity(
    ai_id: str | None = None,
    ai_ids: list[str] | None = None,
    persistent_id: str | None = None,
    persistent_ids: list[str] | None = None,
) -> str:
    """Hide everything except the named entities (or current selection if none given).

    Hide is undoable — use show_all (or undo) to restore. Useful for focusing
    the live view on a specific component while AI work proceeds.
    """
    params: dict[str, Any] = {}
    if ai_id          is not None: params["ai_id"]          = ai_id
    if ai_ids         is not None: params["ai_ids"]         = ai_ids
    if persistent_id  is not None: params["persistent_id"]  = persistent_id
    if persistent_ids is not None: params["persistent_ids"] = persistent_ids
    return json.dumps(_call("view.isolate", params), indent=2)


@mcp.tool()
def show_all() -> str:
    """Un-hide every hidden top-level entity (reverse of isolate_entity)."""
    return json.dumps(_call("view.unisolate"), indent=2)


# ===========================================================================
# DIMENSION TOOLS
# ===========================================================================


@mcp.tool()
def create_dimension(
    ai_id: str,
    start_pt: list[float],
    end_pt: list[float],
    offset_vector: list[float] | None = None,
) -> str:
    """Add a linear dimension to the model.

    Args:
        ai_id: Unique identifier
        start_pt: Start point [x,y,z] in inches
        end_pt: End point [x,y,z] in inches
        offset_vector: Offset direction [x,y,z] (default [0,-10,0])
    """
    params: dict[str, Any] = {
        "ai_id": ai_id,
        "start_pt": start_pt,
        "end_pt": end_pt,
    }
    if offset_vector:
        params["offset_vector"] = offset_vector
    result = _call("ops.dimension.create", params)
    return json.dumps(result, indent=2)


# ===========================================================================
# PARSER TOOLS
# ===========================================================================

@mcp.tool()
def parse_dxf_plan(
    filepath: str,
    layer_name: str = "",
    default_thickness_mm: float = 200.0,
    default_height_mm: float = 2500.0,
    scale_factor: float = 1.0,
) -> str:
    """Extract walls from a 2D DXF floorplan.
    
    Returns a list of wall creation dictionaries that can be fed into batch_operations.
    
    Args:
        filepath: Absolute path to the .dxf file
        layer_name: If specified, only extract from this layer (e.g. "WALLS")
        default_thickness_mm: Wall thickness to apply (default 200)
        default_height_mm: Wall height to apply (default 2500)
        scale_factor: Multiplier to convert DXF drawing units to mm (e.g., 1000 for meters)
    """
    try:
        from su_mcp_bridge.parser.dxf import parse_dxf_walls
        layer_arg = layer_name if layer_name else None
        walls = parse_dxf_walls(
            filepath=filepath,
            layer_name=layer_arg,
            default_thickness_mm=default_thickness_mm,
            default_height_mm=default_height_mm,
            scale_factor=scale_factor,
        )
        return json.dumps({"status": "parsed", "wall_count": len(walls), "walls": walls}, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to parse DXF: {e}"})


# ===========================================================================
# DEEP SCAN & REPORTING TOOLS
# ===========================================================================


@mcp.tool()
def deep_scan(
    limit: int | None = None,
    offset: int = 0,
    include_attrs: bool = False,
    type_filter: str | None = None,
) -> str:
    """Perform a comprehensive deep scan of the SketchUp model.

    Returns entities with full metadata: type, layer, material, bounds (mm),
    volume, face/edge counts, solid status, and attached specs.

    Use limit/offset to page through large models without overloading the
    WebSocket message. Use include_attrs to embed BIM dictionaries inline
    and avoid separate get_entity_attribute calls.

    Args:
        limit: Max entities to return (omit for all). Use 25–100 for large models.
        offset: Skip first N entities (for pagination, default 0).
        include_attrs: If True, embed all attribute dictionaries (except
            internal su_mcp_bridge) on each entity under "attrs". Eliminates
            N+1 attribute lookups. Default False.
        type_filter: Only return entities of this type — "wall", "slab",
            "roof", "primitive", "component", etc.
    """
    params: dict[str, Any] = {"offset": offset, "include_attrs": include_attrs}
    if limit is not None:
        params["limit"] = limit
    if type_filter:
        params["type_filter"] = type_filter
    result = _call("query.deep_scan", params)
    return json.dumps(result, indent=2)


@mcp.tool()
def generate_report(format: str = "md") -> str:
    """Generate a structured report from the current model state.
    
    Args:
        format: Output format - "md" (Markdown), "csv", or "json"
    """
    scan_data = _call("query.deep_scan")
    if isinstance(scan_data, dict) and scan_data.get("error"):
        return json.dumps(scan_data)

    from su_mcp_bridge.core.report import (
        generate_model_report,
        generate_csv_inventory,
        generate_json_snapshot,
    )

    try:
        if format == "csv":
            path = generate_csv_inventory(scan_data)
        elif format == "json":
            path = generate_json_snapshot(scan_data)
        else:
            path = generate_model_report(scan_data)
        return json.dumps({"status": "generated", "path": str(path), "format": format})
    except Exception as e:
        return json.dumps({"error": f"Report generation failed: {e}"})


# ===========================================================================
# EXECUTION TOOLS
# ===========================================================================

@mcp.tool()
def execute_ruby(code: str) -> str:
    """Execute raw arbitrary Ruby code directly inside the SketchUp environment.
    
    WARNING: Use this only when you need to perform complex operations,
    custom math, or access SketchUp Ruby API methods that are not exposed
    by the standard MCP tools.
    
    Args:
        code: A string containing valid SketchUp Ruby code.
    """
    result = _call("ops.execute_ruby", {"code": code})
    return json.dumps(result, indent=2)


# ===========================================================================
# LIFECYCLE TOOLS
# ===========================================================================


@mcp.tool()
def save_file(path: str = "") -> str:
    """Save the active SketchUp model.
    
    Args:
        path: Optional file path to save to. If empty, saves to current location.
    """
    params = {}
    if path:
        params["path"] = path
    else:
        # Auto-route to project model/ folder if active project
        try:
            from su_mcp_bridge.core.project import get_active_project
            project = get_active_project()
            if project:
                auto_path = str(project.model_dir / f"{project.name.replace(' ', '_')}.skp")
                params["path"] = auto_path
        except Exception:
            pass
    result = _call("lifecycle.save", params)
    return json.dumps(result, indent=2)


@mcp.tool()
def save_as(path: str) -> str:
    """Save the model to a new file path.
    
    Args:
        path: Absolute path for the new .skp file
    """
    result = _call("lifecycle.save_as", {"path": path})
    return json.dumps(result, indent=2)


@mcp.tool()
def new_file() -> str:
    """Create a new empty SketchUp model."""
    result = _call("lifecycle.new")
    return json.dumps(result, indent=2)


@mcp.tool()
def open_file(path: str) -> str:
    """Open an existing .skp file in SketchUp.
    
    Args:
        path: Absolute path to the .skp file
    """
    result = _call("lifecycle.open", {"path": path})
    return json.dumps(result, indent=2)


@mcp.tool()
def model_info() -> str:
    """Get detailed information about the current model (path, units, entity count, etc.)."""
    result = _call("lifecycle.model_info")
    return json.dumps(result, indent=2)


# ===========================================================================
# PROJECT MANAGEMENT TOOLS
# ===========================================================================


@mcp.tool()
def create_project(name: str, base_dir: str = "") -> str:
    """Create a new project with a structured folder layout.
    
    Args:
        name: Human-readable project name (e.g. "My House")
        base_dir: Base directory for projects (default: ~/Documents/SU_MCP_Projects)
    """
    from su_mcp_bridge.core.project import create_project as _create
    try:
        ctx = _create(name, base_dir)
        return json.dumps({"status": "created", "project": ctx.to_dict()})
    except Exception as e:
        return json.dumps({"error": f"Failed to create project: {e}"})


@mcp.tool()
def list_all_projects(base_dir: str = "") -> str:
    """List all existing projects.
    
    Args:
        base_dir: Base directory to scan (default: ~/Documents/SU_MCP_Projects)
    """
    from su_mcp_bridge.core.project import list_projects
    projects = list_projects(base_dir)
    return json.dumps({"projects": projects, "total": len(projects)}, indent=2)


@mcp.tool()
def set_active_project(name: str, base_dir: str = "") -> str:
    """Open and set a project as the active context. All captures and reports
    will be auto-routed to this project's folders.
    
    Args:
        name: Project name (fuzzy matched against folder names)
        base_dir: Base directory (default: ~/Documents/SU_MCP_Projects)
    """
    from su_mcp_bridge.core.project import open_project
    ctx = open_project(name, base_dir)
    if ctx:
        return json.dumps({"status": "opened", "project": ctx.to_dict()})
    return json.dumps({"error": f"Project '{name}' not found"})


# ===========================================================================
# CLASH DETECTION TOOLS
# ===========================================================================


@mcp.tool()
def detect_clashes(tolerance_mm: float = 1.0) -> str:
    """Detect geometric clashes (AABB overlaps) between all AI-tracked entities.
    
    Args:
        tolerance_mm: Ignore overlaps smaller than this (default 1mm)
    """
    result = _call("query.clash_detect", {"tolerance_mm": tolerance_mm})
    return json.dumps(result, indent=2)


# ===========================================================================
# WALKTHROUGH & RENDER TOOLS
# ===========================================================================


@mcp.tool()
def generate_walkthrough(
    preset: str = "orbit",
    frames: int = 120,
    fps: int = 30,
    resolution: str = "med",
    save_dir: str = "",
) -> str:
    """Generate an automated camera walkthrough video of the model.
    
    Args:
        preset: Camera motion - "orbit" (360° aerial), "flythrough" (linear path), "cinematic" (smooth arc)
        frames: Number of frames to render (default 120)
        fps: Frames per second for video output (default 30)
        resolution: "low" (640x480), "med" (1280x720), "high" (1920x1080)
        save_dir: Directory for frames and video output
    """
    params: dict[str, Any] = {
        "preset": preset,
        "frames": frames,
        "fps": fps,
        "resolution": resolution,
    }
    if save_dir:
        params["save_dir"] = save_dir
    result = _call("view.walkthrough", params)
    return json.dumps(result, indent=2)


@mcp.tool()
def capture_hq_render(
    preset: str = "iso",
    resolution: str = "ultra",
    save_dir: str = "",
) -> str:
    """Capture a high-quality render of the model (3840x2880 ultra resolution).
    
    Args:
        preset: Camera preset - "plan", "iso", "elev_n", "elev_e", "elev_s", "elev_w"
        resolution: "low", "med", "high", or "ultra" (3840x2880, default)
        save_dir: Output directory
    """
    params: dict[str, Any] = {"preset": preset, "resolution": resolution}
    if save_dir:
        params["save_dir"] = save_dir
    else:
        # Auto-route HQ renders to project assets/ folder
        try:
            from su_mcp_bridge.core.project import get_active_project
            project = get_active_project()
            if project:
                params["save_dir"] = str(project.assets_dir)
        except Exception:
            pass
    result = _call("view.capture", params)
    return json.dumps(result, indent=2)


# ===========================================================================
# ATTRIBUTE DB TOOLS  (Phase 2 — Data Integration)
# ===========================================================================


@mcp.tool()
def get_entity_attribute(
    ai_id: str,
    dict_name: str,
    key: str | None = None,
) -> str:
    """Read one key (or a full dictionary) from an entity's attribute store.

    Args:
        ai_id: Entity identifier (e.g. "W1", "SLAB_GF")
        dict_name: Attribute dictionary name — use "bim" for structural data
        key: Specific key to read; omit to return the entire dictionary
    """
    params: dict[str, Any] = {"ai_id": ai_id, "dict_name": dict_name}
    if key:
        params["key"] = key
    result = _call("query.attr.get", params)
    return json.dumps(result, indent=2)


@mcp.tool()
def list_entity_dictionaries(ai_id: str) -> str:
    """List all attribute dictionary names present on an entity.

    Args:
        ai_id: Entity identifier (e.g. "W1")
    """
    result = _call("query.attr.list", {"ai_id": ai_id})
    return json.dumps(result, indent=2)


@mcp.tool()
def find_entities_by_attribute(
    dict_name: str,
    key: str,
    value: str | None = None,
    entity_type: str | None = None,
    limit: int | None = None,
    depth: int | None = None,
) -> str:
    """Scan all model entities and return those matching an attribute predicate.

    Useful for queries like "find all load-bearing walls" or "find all
    windows with fire_rating = 60min". Use limit on large models to cap
    scan time and return size.

    Args:
        dict_name: Attribute dictionary to search (e.g. "bim")
        key: Attribute key that must exist on the entity
        value: If provided, the key must equal this value (string comparison)
        entity_type: Optional filter — "wall", "slab", "roof", "primitive", etc.
        limit: Stop after N matches (early exit — faster on large models).
        depth: Max recursion depth into nested groups/components (default unlimited).
    """
    params: dict[str, Any] = {"dict_name": dict_name, "key": key}
    if value is not None:
        params["value"] = value
    if entity_type:
        params["type"] = entity_type
    if limit is not None:
        params["limit"] = limit
    if depth is not None:
        params["depth"] = depth
    result = _call("query.attr.find", params)
    return json.dumps(result, indent=2)


@mcp.tool()
def set_entity_attribute(
    ai_id: str,
    dict_name: str,
    key: str,
    value: str | float | bool,
) -> str:
    """Write one key into an attribute dictionary on an entity.

    Use dict_name="bim" to write BIM metadata (structural_role, fire_rating,
    ifc_class, cost_per_unit, etc.) as defined in docs/bim_metadata_schema.md.

    Args:
        ai_id: Target entity identifier
        dict_name: Attribute dictionary name (e.g. "bim")
        key: Attribute key (e.g. "structural_role")
        value: Value to store — string, number, or boolean
    """
    result = _call("ops.attr.set", {
        "ai_id": ai_id,
        "dict_name": dict_name,
        "key": key,
        "value": value,
    })
    return json.dumps(result, indent=2)


@mcp.tool()
def set_entity_attributes_bulk(operations: list[dict]) -> str:
    """Atomically write multiple attributes across multiple entities in one undo step.

    Each operation must have: ai_id, dict_name, key, value.
    All writes succeed or all are rolled back.

    Example operations:
        [
          {"ai_id": "W1", "dict_name": "bim", "key": "structural_role", "value": "load_bearing"},
          {"ai_id": "W2", "dict_name": "bim", "key": "structural_role", "value": "partition"},
          {"ai_id": "W1", "dict_name": "bim", "key": "fire_rating",     "value": "60min"}
        ]

    Args:
        operations: List of {ai_id, dict_name, key, value} dicts
    """
    result = _call("ops.attr.set_bulk", {"operations": operations})
    return json.dumps(result, indent=2)


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    mcp.run(transport="stdio")
