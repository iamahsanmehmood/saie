"""parser/dxf.py — Extract 2D architectural geometry from DXF files.

Uses ezdxf to parse CAD floorplans.
Currently extracts lines and polylines as wall centerlines.
"""

from typing import Any, Dict, List, Optional
import math

try:
    import ezdxf
    from ezdxf.math import Vec2
except ImportError:
    ezdxf = None

from su_mcp_bridge.core.logger import get_logger

log = get_logger(__name__)

def parse_dxf_walls(
    filepath: str,
    layer_name: Optional[str] = None,
    default_thickness_mm: float = 200.0,
    default_height_mm: float = 2500.0,
    scale_factor: float = 1.0,
) -> List[Dict[str, Any]]:
    """Extract walls from a DXF file.
    
    Extracts LINE, POLYLINE, and LWPOLYLINE entities.
    Assume the lines represent wall centerlines.
    
    Args:
        filepath: Path to the .dxf file.
        layer_name: If specified, only extract from this layer.
        default_thickness_mm: Thickness to apply to the extracted walls.
        default_height_mm: Height to apply to the extracted walls.
        scale_factor: Multiplier to convert DXF drawing units to mm (e.g., 1000 if DXF is in meters).
        
    Returns:
        A list of dictionary params ready for `ops.wall.create`.
    """
    if ezdxf is None:
        raise RuntimeError("ezdxf is not installed. Please install it to parse DXF files.")

    try:
        doc = ezdxf.readfile(filepath)
    except IOError as e:
        log.error("Failed to read DXF file %s: %s", filepath, e)
        raise
    except ezdxf.DXFStructureError as e:
        log.error("Invalid DXF structure in %s: %s", filepath, e)
        raise

    msp = doc.modelspace()
    walls = []
    wall_index = 1

    def add_wall(p1, p2):
        nonlocal wall_index
        dx = (p2[0] - p1[0]) * scale_factor
        dy = (p2[1] - p1[1]) * scale_factor
        length = math.hypot(dx, dy)
        if length < 1.0: # skip zero-length walls
            return

        walls.append({
            "id": f"DXF_W{wall_index}",
            "centerline": [
                [p1[0] * scale_factor, p1[1] * scale_factor],
                [p2[0] * scale_factor, p2[1] * scale_factor]
            ],
            "thickness_mm": default_thickness_mm,
            "height_mm": default_height_mm
        })
        wall_index += 1

    for entity in msp:
        if layer_name and entity.dxf.layer != layer_name:
            continue

        etype = entity.dxftype()
        if etype == 'LINE':
            start = entity.dxf.start
            end = entity.dxf.end
            add_wall((start.x, start.y), (end.x, end.y))

        elif etype == 'LWPOLYLINE':
            points = entity.get_points(format='xy')
            for i in range(len(points) - 1):
                add_wall(points[i], points[i+1])
            if entity.closed and len(points) > 2:
                add_wall(points[-1], points[0])

        elif etype == 'POLYLINE':
            points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
            for i in range(len(points) - 1):
                add_wall(points[i], points[i+1])
            if entity.is_closed and len(points) > 2:
                add_wall(points[-1], points[0])

    log.info("Extracted %d walls from %s", len(walls), filepath)
    return walls
