from typing import Literal

from pydantic import BaseModel, Field


class ProjectMeta(BaseModel):
    name: str
    display_units: Literal["mm", "cm", "m", "in", "ft_in"] = "in"
    north_angle_deg: float = 0.0
    site_origin_mm: list[float] = [0.0, 0.0, 0.0]


class Material(BaseModel):
    id: str
    name: str
    color_hex: str | None = None
    texture_path: str | None = None


class Layer(BaseModel):
    id: str
    name: str


# -----------------
# Architectural Entities
# -----------------


class Wall(BaseModel):
    id: str
    level_id: str
    centerline: list[list[float]]  # [[x1, y1], [x2, y2]] in mm
    thickness_mm: float
    height_mm: float
    base_offset_mm: float = 0.0
    material_id_exterior: str | None = None
    material_id_interior: str | None = None
    layer_id: str | None = None
    join_policy: Literal["auto", "miter", "butt"] = "auto"


class Opening(BaseModel):
    id: str
    wall_id: str
    kind: Literal["door", "window", "passage"]
    offset_mm: float
    width_mm: float
    height_mm: float
    sill_mm: float = 0.0
    frame_thickness_mm: float | None = None
    component_id: str | None = None


class Slab(BaseModel):
    id: str
    level_id: str
    polygon: list[list[float]]  # list of [x, y] in mm
    thickness_mm: float
    top_or_bottom: Literal["top", "bottom"] = "top"
    material_id: str | None = None


class Roof(BaseModel):
    id: str
    kind: Literal["flat", "gable", "hip", "shed"]
    footprint: list[list[float]]  # list of [x, y] in mm
    pitch_deg: float
    eave_overhang_mm: float
    ridge_height_mm: float
    material_id: str | None = None


class Column(BaseModel):
    id: str
    level_id: str
    position_mm: list[float]  # [x, y]
    section: dict  # {kind: "rect"|"round", w_mm, d_mm}
    height_mm: float


class Beam(BaseModel):
    id: str
    level_id: str
    start: list[float]  # [x, y, z]
    end: list[float]  # [x, y, z]
    section: dict


class Component(BaseModel):
    id: str
    definition_path: str
    position_mm: list[float]
    rotation_deg: float = 0.0
    scale: list[float] = [1.0, 1.0, 1.0]
    attached_to: str | None = None


class Dimension(BaseModel):
    id: str
    kind: Literal["linear", "angular"]
    from_id: str
    to_id: str
    text: str | None = None


class Level(BaseModel):
    id: str
    name: str
    elevation_mm: float = 0.0
    floor_to_floor_mm: float = 3000.0
    walls: list[Wall] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    slabs: list[Slab] = Field(default_factory=list)
    roofs: list[Roof] = Field(default_factory=list)
    columns: list[Column] = Field(default_factory=list)
    beams: list[Beam] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    dimensions: list[Dimension] = Field(default_factory=list)


# -----------------
# General 3D Entities
# -----------------


class Transform(BaseModel):
    position_mm: list[float] = [0.0, 0.0, 0.0]
    rotation_deg: list[float] = [0.0, 0.0, 0.0]
    scale: list[float] = [1.0, 1.0, 1.0]


class Primitive(BaseModel):
    id: str
    kind: Literal["box", "sphere", "cylinder", "cone", "torus", "pyramid"]
    transform: Transform = Field(default_factory=Transform)
    dimensions: dict
    material_id: str | None = None
    layer_id: str | None = None


class Parametric(BaseModel):
    id: str
    kind: Literal["extrude", "revolve", "sweep", "loft"]
    profile: list[list[float]]
    args: dict
    transform: Transform = Field(default_factory=Transform)
    material_id: str | None = None


class BuildingMetadata(BaseModel):
    created: str = ""
    modified: str = ""
    author: str = ""
    notes: str = ""


# -----------------
# Root Model
# -----------------


class BuildingModel(BaseModel):
    schema_version: str = "2.0"
    project: ProjectMeta
    materials: list[Material] = Field(default_factory=list)
    layers: list[Layer] = Field(default_factory=list)
    levels: list[Level] = Field(default_factory=list)
    primitives: list[Primitive] = Field(default_factory=list)
    parametric: list[Parametric] = Field(default_factory=list)
    metadata: BuildingMetadata = Field(default_factory=BuildingMetadata)
