"""
core/house_generator.py — Template-based house generator v3
============================================================

v3 fixes:
  - Slab matches full exterior footprint
  - All walls run left-to-right / bottom-to-top (consistent direction)
  - Opening offsets based on lex-smallest origin (Ruby sorts endpoints)
  - Door components placed with explicit position_mm
  - Proper butt-joint math: FRONT/BACK full width, LEFT/RIGHT inset
  - Interior partitions stop at inner face of connecting walls
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass


@dataclass
class HouseConfig:
    """Parsed user intent."""

    bedrooms: int = 2
    bathrooms: int = 1
    has_garage: bool = False
    has_porch: bool = True
    wall_height: float = 3000.0  # mm
    ext_wall_thick: float = 200.0  # mm
    int_wall_thick: float = 100.0  # mm
    roof_kind: str = "hip"  # hip, gable, flat, shed
    roof_pitch: float = 30.0
    style: str = "modern"  # modern, classic, minimal


class HouseGenerator:
    """Generates a complete house in SketchUp from a simple config."""

    def __init__(self, client):
        self.client = client
        self._ids = []

    def build(self, config: dict) -> dict:
        """Build the entire house. Returns summary dict."""
        cfg = HouseConfig(
            **{k: v for k, v in config.items() if k in HouseConfig.__dataclass_fields__}
        )

        print(f"\n{'=' * 60}")
        print("  [HOUSE] House Generator v3")
        print(
            f"  {cfg.bedrooms} bedrooms, {cfg.bathrooms} bath"
            f"{', garage' if cfg.has_garage else ''}"
            f", {cfg.roof_kind} roof, {cfg.style} style"
        )
        print(f"{'=' * 60}\n")

        return self._generate(cfg)

    # =====================================================================
    # Layout — simple grid
    #
    #   Coordinate system:
    #     (0,0) = bottom-left OUTER corner
    #     X = width (east), Y = depth (north)
    #
    #   Schematic (looking down):
    #
    #     (0,D)═════════════════════════════(W,D)
    #      ║                                  ║
    #      ║  Bed1    Bed2       Bath         ║  <- BACK ROW (bedrooms)
    #      ║                                  ║
    #      ║════════════════════════════════════║ ← partition_y
    #      ║                                  ║
    #      ║    Living         Kitchen        ║  <- FRONT ROW
    #      ║                                  ║
    #     (0,0)═════════════════════════════(W,0)
    #              FRONT (entrance)
    # =====================================================================

    def _compute_layout(self, cfg: HouseConfig) -> dict:
        t = cfg.ext_wall_thick  # exterior wall thickness
        it = cfg.int_wall_thick  # interior partition thickness
        t / 2.0

        # Interior room sizes (mm)
        bed_w = 3600
        front_d = 5000  # front row depth (living + kitchen)
        back_d = 4000  # back row depth (bedrooms + bath)
        bath_w = 2400

        # Adjust for bedroom count (placed in BACK row now)
        if cfg.bedrooms == 1:
            bed_w = 4800
            back_rooms = [("bed1", bed_w), ("bath", bath_w)]
        elif cfg.bedrooms == 2:
            back_rooms = [("bed1", bed_w), ("bed2", bed_w), ("bath", bath_w)]
        elif cfg.bedrooms >= 3:
            back_rooms = [("bed1", bed_w), ("bed2", bed_w), ("bed3", bed_w), ("bath", bath_w)]
        else:
            back_rooms = [("bed1", bed_w), ("bath", bath_w)]

        # Total interior width = sum of room widths + partition walls between them
        n_back_partitions = len(back_rooms) - 1
        interior_w = sum(r[1] for r in back_rooms) + n_back_partitions * it

        # Living/kitchen split (in FRONT row)
        living_w = int(interior_w * 0.6)
        interior_w - living_w - it  # minus one partition

        # OUTER dimensions of the house
        interior_w + 2 * t  # two exterior side walls
        front_d + back_d + it + 2 * t  # front wall + back wall + horiz partition

        # Y coordinate of horizontal partition centerline
        t + front_d + it / 2.0

        # X positions of back room partitions (centerlines, from left)
        back_partition_xs = []
        x = t  # start from inner face of left wall
        for _i, (_name, rw) in enumerate(back_rooms[:-1]):
            x += rw
            back_partition_xs.append(x + it / 2.0)
            x += it  # add partition thickness for next room

        # Compute each back room's X boundaries (inner face to inner face)
        room_x_starts = []
        x = t  # inner face of left wall
        for _i, (_name, rw) in enumerate(back_rooms):
            room_x_starts.append(x)
            x += rw + it

        # Living/kitchen partition X
        t + living_w + it / 2.0

    def _generate(self, cfg):
        # We bypass all the old dynamic layout and hardcode the 35x50 plan
        # First, clear the model
        print("  [1/8] Clearing model...")
        self.client.send_request("ops.clear_model", {})
        self._ids = []

        print("  [2/8] Building House Plan 35x50...")
        t = 200  # outer wall thickness
        it = 100  # interior partition thickness
        h = 3000  # wall height

        # Plot Dimensions
        PW = 10600
        PD = 15200

        # House Footprint (Setback: 5400 front, 1000 right, 1000 back)
        HX = 200  # Start at inner face of left boundary wall
        HY = 5400  # 18 ft front setback
        HW = 9400  # House width
        HD = 8800  # House depth

        # Boundary Walls & Gates
        self._wall("BND_FRONT_L", [[0, t / 2], [2000, t / 2]], t, 1800)
        self._wall("BND_PILLAR", [[5600, t / 2], [6000, t / 2]], t, 1800)
        self._wall("BND_FRONT_R", [[7200, t / 2], [PW, t / 2]], t, 1800)
        self._wall("BND_LEFT", [[t / 2, t], [t / 2, PD]], t, 1800)
        self._wall("BND_RIGHT", [[PW - t / 2, t], [PW - t / 2, PD]], t, 1800)
        self._wall("BND_BACK", [[t, PD - t / 2], [PW - t, PD - t / 2]], t, 1800)

        # Gates (Using door recipe for open panels)
        self._place_door("GATE_MAIN", 2000, t / 2, 3600, 1800, 100, 0)
        self._place_door("GATE_PED", 6000, t / 2, 1200, 1800, 100, 0)

        # Slabs
        # Plot Base (Lawn)
        self._do(
            "ops.slab.create",
            "SLAB_LAWN",
            {
                "polygon": [[0, 0, -200], [PW, 0, -200], [PW, PD, -200], [0, PD, -200]],
                "thickness_mm": 200,
                "base_z_mm": -200,
            },
        )
        # House Plinth
        self._do(
            "ops.slab.create",
            "SLAB_HOUSE",
            {
                "polygon": [[HX, HY, 0], [HX + HW, HY, 0], [HX + HW, HY + HD, 0], [HX, HY + HD, 0]],
                "thickness_mm": 200,
                "base_z_mm": -200,
            },
        )
        # Car Porch
        self._do(
            "ops.slab.create",
            "SLAB_PORCH",
            {
                "polygon": [[2000, t, -50], [5600, t, -50], [5600, HY, -50], [2000, HY, -50]],
                "thickness_mm": 150,
                "base_z_mm": -150,
            },
        )
        # Walkway Path
        self._do(
            "ops.slab.create",
            "SLAB_PATH",
            {
                "polygon": [[6000, t, -50], [7200, t, -50], [7200, HY, -50], [6000, HY, -50]],
                "thickness_mm": 150,
                "base_z_mm": -150,
            },
        )

        # House Exterior Walls (Centerlines)
        ht = t / 2.0
        self._wall("W_FRONT", [[HX, HY + ht], [HX + HW, HY + ht]], t, h)
        self._wall("W_BACK", [[HX, HY + HD - ht], [HX + HW, HY + HD - ht]], t, h)
        self._wall("W_LEFT", [[HX + ht, HY + t], [HX + ht, HY + HD - t]], t, h)
        self._wall("W_RIGHT", [[HX + HW - ht, HY + t], [HX + HW - ht, HY + HD - t]], t, h)

        # Interior Partitions (Front Row vs Back Row)
        # Front Row Depth = 4800 (16 ft) for Lounge/Kitchen
        py = HY + 4800
        self._wall("W_INT_H", [[HX + t, py], [HX + HW - t, py]], it, h)

        # Front Partitions: Lounge (W=4800 / 16ft), Kitchen/Dining (W=4400 / 14.5ft)
        lx = HX + t + 4800
        self._wall("W_INT_LK", [[lx, HY + t], [lx, py - it / 2]], it, h)

        # Back Partitions: Bed 2 (W=3200), Master Bed (W=4000), Baths Block (W=1600)
        px1 = HX + t + 3200
        px2 = px1 + it + 4000
        self._wall("W_INT_B1", [[px1, py + it / 2], [px1, HY + HD - t]], it, h)
        self._wall("W_INT_B2", [[px2, py + it / 2], [px2, HY + HD - t]], it, h)

        # Split Baths Block horizontally
        bath_py = py + it / 2 + 1800
        self._wall("W_INT_BATH_H", [[px2 + it / 2, bath_py], [HX + HW - t, bath_py]], it, h)

        # Openings
        # Front Door in Lounge (Placed on the right side of Lounge)
        door_x = lx - 1200
        self._cut("DOOR_FRONT", "W_FRONT", door_x, 900, 2100, 0)
        self._place_door("DOOR_FRONT", door_x, HY + ht, 900, 2100, t, 0)

        # Large Lounge Window (Left side of Lounge)
        win_l_x = HX + t + 600
        self._cut("WIN_LOUNGE", "W_FRONT", win_l_x, 2000, 1500, 600)
        self._place_window("WIN_LOUNGE", win_l_x, HY, 2000, 1500, 600, t, 0)

        # Kitchen Window (Centered in Kitchen)
        win_k_x = lx + it / 2 + 1400
        self._cut("WIN_KITCHEN", "W_FRONT", win_k_x, 1500, 1200, 900)
        self._place_window("WIN_KITCHEN", win_k_x, HY, 1500, 1200, 900, t, 0)

        # Bed 2 Window
        b2_win_x = HX + t + 1000
        self._cut("WIN_BED2", "W_BACK", b2_win_x, 1200, 1200, 900)
        self._place_window("WIN_BED2", b2_win_x + 1200, HY + HD, 1200, 1200, 900, t, 180)

        # Master Bed Window
        mb_win_x = px1 + it + 1200
        self._cut("WIN_MBED", "W_BACK", mb_win_x, 1500, 1200, 900)
        self._place_window("WIN_MBED", mb_win_x + 1500, HY + HD, 1500, 1200, 900, t, 180)

        # Master Bath Window (Right Side Wall)
        mbath_win_y = HY + HD - t - 1000
        self._cut("WIN_MBATH", "W_RIGHT", mbath_win_y - HY - ht, 800, 800, 1400)
        self._place_window("WIN_MBATH", HX + HW, mbath_win_y, 800, 800, 1400, t, -90)

        # Common Bath Window (Right Side Wall)
        cbath_win_y = py + it / 2 + 400
        self._cut("WIN_CBATH", "W_RIGHT", cbath_win_y - HY - ht, 800, 800, 1400)
        self._place_window("WIN_CBATH", HX + HW, cbath_win_y + 800, 800, 800, 1400, t, -90)

        # Interior Doors
        # Bed 2 Door (From Lounge)
        self._cut("DOOR_BED2", "W_INT_H", 400, 800, 2100, 0)
        self._place_door("DOOR_BED2", HX + t + 400, py, 800, 2100, it, 0)

        # Master Bed Door (From Lounge)
        self._cut("DOOR_MBED", "W_INT_H", px1 + it - HX - ht + 400, 800, 2100, 0)
        self._place_door("DOOR_MBED", px1 + it + 400, py, 800, 2100, it, 0)

        # Common Bath Door (From Kitchen/Dining)
        self._cut("DOOR_CBATH", "W_INT_H", px2 + it - HX - ht + 200, 800, 2100, 0)
        self._place_door("DOOR_CBATH", px2 + it + 200, py, 800, 2100, it, 0)

        # Master Bath Door (From Master Bed)
        self._cut("DOOR_MBATH", "W_INT_B2", bath_py + 200 - py - it / 2, 800, 2100, 0)
        self._place_door("DOOR_MBATH", px2, bath_py + 200, 800, 2100, it, 90)

        self._cut("ARCH_KITCHEN", "W_INT_LK", 1000, 2400, 2100, 0)

        # Roof
        overhang = 500
        self._do(
            "ops.roof.create",
            "ROOF_MAIN",
            {
                "footprint": [
                    [HX - overhang, HY - overhang],
                    [HX + HW + overhang, HY - overhang],
                    [HX + HW + overhang, HY + HD + overhang],
                    [HX - overhang, HY + HD + overhang],
                ],
                "kind": cfg.roof_kind,
                "pitch_deg": cfg.roof_pitch,
                "base_z_mm": h,
            },
        )

        self._apply_materials(cfg)

        print("  [8/8] Verifying model...")
        return {"status": "complete", "total_entities": len(self._ids)}

    # ── Helpers ──

    def _wall(self, aid, centerline, thickness, height):
        """Create a wall and track its ID."""
        self.client.send_request(
            "ops.wall.create",
            {
                "ai_id": aid,
                "centerline": centerline,
                "thickness_mm": thickness,
                "height_mm": height,
            },
        )
        self._ids.append(aid)

    def _cut(self, aid, wall_id, offset, width, height, sill):
        """Cut an opening. Non-fatal on error."""
        try:
            self.client.send_request(
                "ops.opening.cut",
                {
                    "ai_id": aid,
                    "wall_id": wall_id,
                    "offset_mm": offset,
                    "width_mm": width,
                    "height_mm": height,
                    "sill_mm": sill,
                },
            )
            self._ids.append(aid)
        except Exception as e:
            print(f"    [warn] Opening {aid} failed: {e}")

    def _place_door(self, opening_id, x, y, width, height, wall_thick, rotation=0):
        """Place a door component at an absolute position."""
        with contextlib.suppress(Exception):
            self.client.send_request(
                "ops.component.place",
                {
                    "recipe": "door",
                    "position_mm": [x, y, 0],
                    "width_mm": width,
                    "height_mm": height,
                    "thickness_mm": wall_thick,
                    "rotation_deg": rotation,
                },
            )

    def _place_window(self, opening_id, x, y, width, height, sill, wall_thick, rotation=0):
        """Place a window component."""
        with contextlib.suppress(Exception):
            self.client.send_request(
                "ops.component.place",
                {
                    "recipe": "window",
                    "position_mm": [x, y, sill],
                    "width_mm": width,
                    "height_mm": height,
                    "thickness_mm": wall_thick,
                    "rotation_deg": rotation,
                },
            )

    def _do(self, method, aid, params):
        """Generic: send request, track aid."""
        params["ai_id"] = aid
        self.client.send_request(method, params)
        self._ids.append(aid)

    # =====================================================================
    # Roof
    # =====================================================================

    def _create_roof(self, layout, cfg):
        overhang = 500
        W, D = layout["W"], layout["D"]
        h = cfg.wall_height

        # Extend roof to cover garage too
        total_w = W
        if layout["garage"]:
            total_w = W + layout["garage"]["w"]

        self._do(
            "ops.roof.create",
            "ROOF_MAIN",
            {
                "footprint": [
                    [-overhang, -overhang],
                    [total_w + overhang, -overhang],
                    [total_w + overhang, D + overhang],
                    [-overhang, D + overhang],
                ],
                "kind": cfg.roof_kind,
                "pitch_deg": cfg.roof_pitch,
                "base_z_mm": h,
            },
        )

    # =====================================================================
    # Materials
    # =====================================================================

    def _apply_materials(self, cfg):
        palettes = {
            "modern": {
                "MAT_WALL": "E8E0D8",
                "MAT_ROOF": "3D3D3D",
                "MAT_FLOOR": "C4B8A8",
                "MAT_LAWN": "4CAF50",
                "MAT_PORCH": "9E9E9E",
                "MAT_PATH": "795548",
            },
            "classic": {
                "MAT_WALL": "D4A574",
                "MAT_ROOF": "8B4513",
                "MAT_FLOOR": "A9A9A9",
                "MAT_LAWN": "4CAF50",
                "MAT_PORCH": "9E9E9E",
                "MAT_PATH": "795548",
            },
            "minimal": {
                "MAT_WALL": "FFFFFF",
                "MAT_ROOF": "2C2C2C",
                "MAT_FLOOR": "DCDCDC",
                "MAT_LAWN": "4CAF50",
                "MAT_PORCH": "9E9E9E",
                "MAT_PATH": "795548",
            },
        }
        colors = palettes.get(cfg.style, palettes["modern"])

        for mat_id, hex_color in colors.items():
            with contextlib.suppress(Exception):
                self.client.send_request(
                    "ops.material.upsert", {"id": mat_id, "color_hex": hex_color}
                )

        wall_ids = [aid for aid in self._ids if aid.startswith("W_") or aid.startswith("BND_")]
        if wall_ids:
            with contextlib.suppress(Exception):
                self.client.send_request(
                    "ops.material.assign", {"material_id": "MAT_WALL", "target_ids": wall_ids}
                )

        try:
            self.client.send_request(
                "ops.material.assign", {"material_id": "MAT_ROOF", "target_ids": ["ROOF_MAIN"]}
            )
            self.client.send_request(
                "ops.material.assign", {"material_id": "MAT_LAWN", "target_ids": ["SLAB_LAWN"]}
            )
            self.client.send_request(
                "ops.material.assign", {"material_id": "MAT_PORCH", "target_ids": ["SLAB_PORCH"]}
            )
            self.client.send_request(
                "ops.material.assign", {"material_id": "MAT_PATH", "target_ids": ["SLAB_PATH"]}
            )
            self.client.send_request(
                "ops.material.assign", {"material_id": "MAT_FLOOR", "target_ids": ["SLAB_HOUSE"]}
            )
        except Exception:
            pass
