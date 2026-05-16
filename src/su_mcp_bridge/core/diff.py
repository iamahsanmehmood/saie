from typing import Any

from pydantic import BaseModel

from .model import BuildingModel


class FieldChange(BaseModel):
    field: str
    old_value: Any
    new_value: Any


class EntityCreated(BaseModel):
    entity_id: str
    entity_type: str
    data: dict


class EntityDeleted(BaseModel):
    entity_id: str
    entity_type: str


class EntityModified(BaseModel):
    entity_id: str
    entity_type: str
    changes: list[FieldChange]


class ChangeSet(BaseModel):
    created: list[EntityCreated] = []
    deleted: list[EntityDeleted] = []
    modified: list[EntityModified] = []

    def is_empty(self) -> bool:
        return len(self.created) == 0 and len(self.deleted) == 0 and len(self.modified) == 0


# Fields on a Level that are nested entity lists -- these are diffed
# independently at the top-level diff_models loop, so we ignore them when
# field-diffing the Level itself.
_LEVEL_NESTED_FIELDS = frozenset(
    {
        "walls",
        "openings",
        "slabs",
        "roofs",
        "columns",
        "beams",
        "components",
        "dimensions",
    }
)


def _is_nested_entity_list(field_name: str, entity_type: str, value: Any, old_value: Any) -> bool:
    """A field whose CONTENTS are diffed as their own typed entities elsewhere."""
    if entity_type == "Level" and field_name in _LEVEL_NESTED_FIELDS:
        return True
    # Heuristic fallback: list of dicts with 'id' on either side.
    for candidate in (value, old_value):
        if (
            isinstance(candidate, list)
            and candidate
            and isinstance(candidate[0], dict)
            and "id" in candidate[0]
        ):
            return True
    return False


def _diff_entities(
    old_entities: list[Any], new_entities: list[Any], entity_type: str, changeset: ChangeSet
):
    old_dict = {e.id: e for e in old_entities}
    new_dict = {e.id: e for e in new_entities}

    # Check for created or modified
    for eid, new_e in new_dict.items():
        if eid not in old_dict:
            changeset.created.append(
                EntityCreated(entity_id=eid, entity_type=entity_type, data=new_e.model_dump())
            )
        else:
            old_e = old_dict[eid]
            old_dump = old_e.model_dump()
            new_dump = new_e.model_dump()

            changes = []
            for k, v in new_dump.items():
                if k not in old_dump:
                    continue
                if old_dump[k] == v:
                    continue
                if _is_nested_entity_list(k, entity_type, v, old_dump[k]):
                    continue
                changes.append(FieldChange(field=k, old_value=old_dump[k], new_value=v))

            if changes:
                changeset.modified.append(
                    EntityModified(entity_id=eid, entity_type=entity_type, changes=changes)
                )

    # Check for deleted
    for eid in old_dict:
        if eid not in new_dict:
            changeset.deleted.append(EntityDeleted(entity_id=eid, entity_type=entity_type))


def diff_models(old_model: BuildingModel, new_model: BuildingModel) -> ChangeSet:
    """
    Compares two BuildingModels and returns a typed ChangeSet.
    """
    cs = ChangeSet()

    _diff_entities(old_model.materials, new_model.materials, "Material", cs)
    _diff_entities(old_model.layers, new_model.layers, "Layer", cs)
    _diff_entities(old_model.levels, new_model.levels, "Level", cs)

    # Since walls, openings, slabs are nested inside levels, we need to extract them all first
    old_walls = [w for lvl in old_model.levels for w in lvl.walls]
    new_walls = [w for lvl in new_model.levels for w in lvl.walls]
    _diff_entities(old_walls, new_walls, "Wall", cs)

    old_openings = [o for lvl in old_model.levels for o in lvl.openings]
    new_openings = [o for lvl in new_model.levels for o in lvl.openings]
    _diff_entities(old_openings, new_openings, "Opening", cs)

    old_slabs = [s for lvl in old_model.levels for s in lvl.slabs]
    new_slabs = [s for lvl in new_model.levels for s in lvl.slabs]
    _diff_entities(old_slabs, new_slabs, "Slab", cs)

    # ... Diff Roofs, Columns, Beams, Components, Dimensions, Primitives, Parametric
    old_prims = old_model.primitives
    new_prims = new_model.primitives
    _diff_entities(old_prims, new_prims, "Primitive", cs)

    old_params = old_model.parametric
    new_params = new_model.parametric
    _diff_entities(old_params, new_params, "Parametric", cs)

    return cs
