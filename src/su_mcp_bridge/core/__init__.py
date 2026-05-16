"""su_mcp_bridge.core — BuilderCore: deterministic project/state engine.

Public API:
    BuildingModel, Wall, Opening, Slab, Roof, Column, Beam, Component,
    Dimension, Level, Material, Layer, Primitive, Parametric, ProjectMeta
    validate_model, ValidationIssue
    diff_models, ChangeSet, EntityCreated, EntityModified, EntityDeleted, FieldChange
    changeset_to_ops
    Project/ProjectContext, ProjectLockError
    History, OpRecord
    mm_to_in, in_to_mm, point_mm_to_in, polygon_mm_to_in
    wall_length_mm, polygon_area_mm, polygon_is_simple, polygon_is_ccw
    get_logger
"""

from .model import (
    BuildingModel,
    Wall,
    Opening,
    Slab,
    Roof,
    Column,
    Beam,
    Component,
    Dimension,
    Level,
    Material,
    Layer,
    Primitive,
    Parametric,
    Transform,
    ProjectMeta,
    BuildingMetadata,
)
from .validate import validate_model, ValidationIssue, ValidationError
from .diff import (
    diff_models,
    ChangeSet,
    EntityCreated,
    EntityModified,
    EntityDeleted,
    FieldChange,
)
from .apply import changeset_to_ops, index_entities_by_id
from .project import (
    ProjectContext,
    create_project,
    list_projects,
    open_project,
    get_active_project,
    Project,
    ProjectLockError,
    empty_model,
)
try:
    from .history import History, OpRecord
except ImportError:
    History = None
    OpRecord = None
from .units import (
    mm_to_in,
    in_to_mm,
    point_mm_to_in,
    point_in_to_mm,
    polygon_mm_to_in,
    polygon_in_to_mm,
)
from .geometry import (
    wall_length_mm,
    polygon_area_mm,
    polygon_is_simple,
    polygon_is_ccw,
    polygon_centroid_mm,
    point_in_polygon_mm,
    miter_angle_deg,
)
from .logger import get_logger

__all__ = [
    # model
    "BuildingModel",
    "Wall",
    "Opening",
    "Slab",
    "Roof",
    "Column",
    "Beam",
    "Component",
    "Dimension",
    "Level",
    "Material",
    "Layer",
    "Primitive",
    "Parametric",
    "Transform",
    "ProjectMeta",
    "BuildingMetadata",
    # validate
    "validate_model",
    "ValidationIssue",
    "ValidationError",
    # diff
    "diff_models",
    "ChangeSet",
    "EntityCreated",
    "EntityModified",
    "EntityDeleted",
    "FieldChange",
    # apply
    "changeset_to_ops",
    "index_entities_by_id",
    # project
    "ProjectContext",
    "create_project",
    "list_projects",
    "open_project",
    "get_active_project",
    "Project",
    "ProjectLockError",
    "empty_model",
    # history
    "History",
    "OpRecord",
    # units
    "mm_to_in",
    "in_to_mm",
    "point_mm_to_in",
    "point_in_to_mm",
    "polygon_mm_to_in",
    "polygon_in_to_mm",
    # geometry
    "wall_length_mm",
    "polygon_area_mm",
    "polygon_is_simple",
    "polygon_is_ccw",
    "polygon_centroid_mm",
    "point_in_polygon_mm",
    "miter_angle_deg",
    # logger
    "get_logger",
]
