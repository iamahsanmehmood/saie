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

from .apply import changeset_to_ops, index_entities_by_id
from .diff import (
    ChangeSet,
    EntityCreated,
    EntityDeleted,
    EntityModified,
    FieldChange,
    diff_models,
)
from .model import (
    Beam,
    BuildingMetadata,
    BuildingModel,
    Column,
    Component,
    Dimension,
    Layer,
    Level,
    Material,
    Opening,
    Parametric,
    Primitive,
    ProjectMeta,
    Roof,
    Slab,
    Transform,
    Wall,
)
from .project import (
    Project,
    ProjectContext,
    ProjectLockError,
    create_project,
    empty_model,
    get_active_project,
    list_projects,
    open_project,
)
from .validate import ValidationError, ValidationIssue, validate_model

try:
    from .history import History, OpRecord
except ImportError:
    History = None
    OpRecord = None
from .geometry import (
    miter_angle_deg,
    point_in_polygon_mm,
    polygon_area_mm,
    polygon_centroid_mm,
    polygon_is_ccw,
    polygon_is_simple,
    wall_length_mm,
)
from .logger import get_logger
from .units import (
    in_to_mm,
    mm_to_in,
    point_in_to_mm,
    point_mm_to_in,
    polygon_in_to_mm,
    polygon_mm_to_in,
)

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
