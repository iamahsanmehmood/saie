from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal

class ProjectMeta(BaseModel):
    name: str
    display_units: Literal["mm", "cm", "m", "in", "ft_in"] = "in"
    north_angle_deg: float = 0.0
    site_origin_mm: List[float] = [0.0, 0.0, 0.0]

class Material(BaseModel):
    id: str
    name: str
    color_hex: Optional[str] = None
    texture_path: Optional[str] = None

class Layer(BaseModel):
    id: str
    name: str

# -----------------
# Architectural Entities
# -----------------

class Wall(BaseModel):
    id: str
    level_id: str
    centerline: List[List[float]] # [[x1, y1], [x2, y2]] in mm
    thickness_mm: float
    height_mm: float
    base_offset_mm: float = 0.0
    material_id_exterior: Optional[str] = None
    material_id_interior: Optional[str] = None
    layer_id: Optional[str] = None
    join_policy: Literal["auto", "miter", "butt"] = "auto"

class Opening(BaseModel):
    id: str
    wall_id: str
    kind: Literal["door", "window", "passage"]
    offset_mm: float
    width_mm: float
    height_mm: float
    sill_mm: float = 0.0
    frame_thickness_mm: Optional[float] = None
    component_id: Optional[str] = None

class Slab(BaseModel):
    id: str
    level_id: str
    polygon: List[List[float]] # list of [x, y] in mm
    thickness_mm: float
    top_or_bottom: Literal["top", "bottom"] = "top"
    material_id: Optional[str] = None

class Roof(BaseModel):
    id: str
    kind: Literal["flat", "gable", "hip", "shed"]
    footprint: List[List[float]] # list of [x, y] in mm
    pitch_deg: float
    eave_overhang_mm: float
    ridge_height_mm: float
    material_id: Optional[str] = None

class Column(BaseModel):
    id: str
    level_id: str
    position_mm: List[float] # [x, y]
    section: dict # {kind: "rect"|"round", w_mm, d_mm}
    height_mm: float

class Beam(BaseModel):
    id: str
    level_id: str
    start: List[float] # [x, y, z]
    end: List[float] # [x, y, z]
    section: dict

class Component(BaseModel):
    id: str
    definition_path: str
    position_mm: List[float]
    rotation_deg: float = 0.0
    scale: List[float] = [1.0, 1.0, 1.0]
    attached_to: Optional[str] = None

class Dimension(BaseModel):
    id: str
    kind: Literal["linear", "angular"]
    from_id: str
    to_id: str
    text: Optional[str] = None

class Level(BaseModel):
    id: str
    name: str
    elevation_mm: float = 0.0
    floor_to_floor_mm: float = 3000.0
    walls: List[Wall] = Field(default_factory=list)
    openings: List[Opening] = Field(default_factory=list)
    slabs: List[Slab] = Field(default_factory=list)
    roofs: List[Roof] = Field(default_factory=list)
    columns: List[Column] = Field(default_factory=list)
    beams: List[Beam] = Field(default_factory=list)
    components: List[Component] = Field(default_factory=list)
    dimensions: List[Dimension] = Field(default_factory=list)

# -----------------
# General 3D Entities
# -----------------

class Transform(BaseModel):
    position_mm: List[float] = [0.0, 0.0, 0.0]
    rotation_deg: List[float] = [0.0, 0.0, 0.0]
    scale: List[float] = [1.0, 1.0, 1.0]

class Primitive(BaseModel):
    id: str
    kind: Literal["box", "sphere", "cylinder", "cone", "torus", "pyramid"]
    transform: Transform = Field(default_factory=Transform)
    dimensions: dict
    material_id: Optional[str] = None
    layer_id: Optional[str] = None

class Parametric(BaseModel):
    id: str
    kind: Literal["extrude", "revolve", "sweep", "loft"]
    profile: List[List[float]]
    args: dict
    transform: Transform = Field(default_factory=Transform)
    material_id: Optional[str] = None

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
    materials: List[Material] = Field(default_factory=list)
    layers: List[Layer] = Field(default_factory=list)
    levels: List[Level] = Field(default_factory=list)
    primitives: List[Primitive] = Field(default_factory=list)
    parametric: List[Parametric] = Field(default_factory=list)
    metadata: BuildingMetadata = Field(default_factory=BuildingMetadata)
