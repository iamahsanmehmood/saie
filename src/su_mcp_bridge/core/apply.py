"""core/apply.py — Diff-to-Ops Translator.

Takes a `ChangeSet` from `diff.py` and converts it into an ordered list of
JSON-RPC operations the SketchUp bridge can execute via `ops.batch`.

Phase order (deletes -> modifies -> creates) and within each, a fixed entity
order (materials -> layers -> walls -> openings -> slabs -> roofs ->
columns -> beams -> components -> primitives -> parametric -> dimensions)
so deletions free space before creations and dependent entities (openings)
are mutated after their parents (walls).

Modifications use a delete-then-recreate strategy because SketchUp's
boolean-subtract semantics make in-place geometry edits unreliable. The
resulting wall keeps its `ai_id` because we re-create with the same id.
"""

from __future__ import annotations

import math
from typing import Any

from .diff import ChangeSet, EntityCreated, EntityDeleted, EntityModified
from .geometry import resolve_butt_joints
from .logger import get_logger

log = get_logger(__name__)

# Phase order for batched application. Earlier groups are applied first.
# Within a phase we order: deletes, then modifies, then creates.
_ENTITY_PHASE_ORDER: list[str] = [
    "Material",
    "Layer",
    "Level",
    "Wall",
    "Opening",
    "Slab",
    "Roof",
    "Column",
    "Beam",
    "Component",
    "Primitive",
    "Parametric",
    "Dimension",
]


def _phase_index(entity_type: str) -> int:
    try:
        return _ENTITY_PHASE_ORDER.index(entity_type)
    except ValueError:
        return len(_ENTITY_PHASE_ORDER)  # unknown -> last


# ---------------------------------------------------------------------------
# Per-entity translators (pure functions: dict -> dict)
# ---------------------------------------------------------------------------


def _wall_create_op(
    data: dict[str, Any], adjusted_centerlines: dict[str, list[list[float]]] = None
) -> dict[str, Any]:
    centerline = data["centerline"]
    if adjusted_centerlines and data["id"] in adjusted_centerlines:
        centerline = adjusted_centerlines[data["id"]]

    return {
        "method": "ops.wall.create",
        "params": {
            "ai_id": data["id"],
            "centerline": centerline,
            "thickness_mm": data["thickness_mm"],
            "height_mm": data["height_mm"],
            "level": data.get("level_id", "GF"),
        },
    }


def _opening_create_op(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": "ops.opening.cut",
        "params": {
            "ai_id": data["id"],
            "wall_id": data["wall_id"],
            "offset_mm": data["offset_mm"],
            "width_mm": data["width_mm"],
            "height_mm": data["height_mm"],
            "sill_mm": data.get("sill_mm", 0.0),
            "kind": data.get("kind", "passage"),
        },
    }


def _slab_create_op(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": "ops.slab.create",
        "params": {
            "ai_id": data["id"],
            "polygon": data["polygon"],
            "thickness_mm": data["thickness_mm"],
            "top_or_bottom": data.get("top_or_bottom", "top"),
            "base_z_mm": data.get("base_offset_mm", 0.0),
        },
    }


def _roof_create_op(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": "ops.roof.create",
        "params": {
            "ai_id": data["id"],
            "kind": data["kind"],
            "footprint": data["footprint"],
            "pitch_deg": data.get("pitch_deg", 30.0),
            "eave_overhang_mm": data.get("eave_overhang_mm", 0.0),
            "ridge_height_mm": data.get("ridge_height_mm", 0.0),
        },
    }


def _primitive_create_op(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": "ops.primitive.create",
        "params": {
            "ai_id": data["id"],
            "kind": data["kind"],
            "dimensions": data["dimensions"],
            "transform": data.get("transform") or {},
        },
    }


def _component_create_op(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": "ops.component.place",
        "params": {
            "ai_id": data["id"],
            "definition_path": data["definition_path"],
            "position_mm": data["position_mm"],
            "rotation_deg": data.get("rotation_deg", 0.0),
            "scale": data.get("scale", [1.0, 1.0, 1.0]),
            "attached_to": data.get("attached_to"),
        },
    }


def _material_upsert_op(data: dict[str, Any]) -> dict[str, Any]:
    return {"method": "ops.material.upsert", "params": data}


def _layer_upsert_op(data: dict[str, Any]) -> dict[str, Any]:
    return {"method": "ops.layer.upsert", "params": data}


_CREATE_DISPATCH = {
    "Wall": _wall_create_op,
    "Opening": _opening_create_op,
    "Slab": _slab_create_op,
    "Roof": _roof_create_op,
    "Primitive": _primitive_create_op,
    "Component": _component_create_op,
    "Material": _material_upsert_op,
    "Layer": _layer_upsert_op,
}


def _create_op(created: EntityCreated, context: dict[str, Any] = None) -> dict[str, Any]:
    """Convert an EntityCreated into an ops.* call."""
    factory = _CREATE_DISPATCH.get(created.entity_type)
    if factory is None:
        log.warning(
            "apply: no create handler for entity_type=%s id=%s",
            created.entity_type,
            created.entity_id,
        )
        return {
            "method": "ops.unknown.create",
            "params": {
                "ai_id": created.entity_id,
                "type": created.entity_type,
                "data": created.data,
            },
        }
    if created.entity_type == "Wall":
        return factory(created.data, context.get("adjusted_centerlines") if context else None)
    return factory(created.data)


def _delete_op(deleted: EntityDeleted) -> dict[str, Any]:
    return {
        "method": "ops.delete",
        "params": {
            "ai_id": deleted.entity_id,
            "entity_type": deleted.entity_type,
        },
    }


def _modify_ops(
    modified: EntityModified, new_data: dict[str, Any], context: dict[str, Any] = None
) -> list[dict[str, Any]]:
    """Convert a modification into delete+recreate ops.

    SketchUp boolean ops make in-place geometry edits flaky. The simplest
    reliable strategy is to erase the old entity and reconstruct it with
    the same `ai_id` from the new model state. The new wall (or whatever)
    keeps its identity because the `ai_id` is identical; downstream openings
    can still be re-cut against it.

    `new_data` is the full new dict for the modified entity, sourced from
    the new BuildingModel. Pass-through dispatches it as a creation.
    """
    factory = _CREATE_DISPATCH.get(modified.entity_type)
    if factory is None:
        log.warning(
            "apply: cannot modify entity_type=%s (no recreate handler)",
            modified.entity_type,
        )
        return [
            _delete_op(
                EntityDeleted(entity_id=modified.entity_id, entity_type=modified.entity_type)
            )
        ]

    if modified.entity_type == "Wall":
        create_call = factory(new_data, context.get("adjusted_centerlines") if context else None)
    else:
        create_call = factory(new_data)

    return [
        _delete_op(EntityDeleted(entity_id=modified.entity_id, entity_type=modified.entity_type)),
        create_call,
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def changeset_to_ops(
    changeset: ChangeSet,
    new_entities_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Translate a ChangeSet into an ordered list of ops.

    Args:
        changeset: typed diff between the old and new BuildingModels.
        new_entities_by_id: lookup table {entity_id -> dict} for the NEW
            model state. Required if the changeset has any `modified`
            entries, because modifications need the new field values.
            Build with `index_entities_by_id(new_model)` below.

    Returns:
        A list of {"method": str, "params": dict} ready for `ops.batch`.
    """
    new_entities_by_id = new_entities_by_id or {}
    ops: list[dict[str, Any]] = []

    # Calculate adjusted centerlines ONLY for explicit Wall entities
    walls_in_new_state = [
        data for data in new_entities_by_id.values() if data.get("_type") == "Wall"
    ]
    adjusted_centerlines = resolve_butt_joints(walls_in_new_state) if walls_in_new_state else {}
    context = {"adjusted_centerlines": adjusted_centerlines}

    # 1. Deletes first, ordered by phase ascending.
    deletes = sorted(changeset.deleted, key=lambda d: (_phase_index(d.entity_type), d.entity_id))
    for d in deletes:
        ops.append(_delete_op(d))

    # 2. Modifies next.
    modifies = sorted(changeset.modified, key=lambda m: (_phase_index(m.entity_type), m.entity_id))
    for m in modifies:
        new_data = new_entities_by_id.get(m.entity_id)
        if new_data is None:
            log.warning(
                "apply: no new data for modified entity %s; emitting delete only",
                m.entity_id,
            )
            ops.append(_delete_op(EntityDeleted(entity_id=m.entity_id, entity_type=m.entity_type)))
            continue
        ops.extend(_modify_ops(m, new_data, context))

    # 3. Creates last, ordered by phase ascending.
    creates = sorted(changeset.created, key=lambda c: (_phase_index(c.entity_type), c.entity_id))
    for c in creates:
        ops.append(_create_op(c, context))

    return ops


def dispatch_in_chunks(
    ops: list[dict[str, Any]],
    client: Any,
    chunk_size: int = 50,
    mode: str = "atomic",
) -> list[dict[str, Any]]:
    """Dispatch a large op list as sequential chunked batches.

    A single ops.batch with 500 ops can time out or make SketchUp unresponsive.
    This splits the list into chunks of `chunk_size`, sends each as its own
    ops.batch call with an adaptive timeout, and collects the results.

    Args:
        ops: Full ordered op list from changeset_to_ops().
        client: Connected SketchUpWSClient instance.
        chunk_size: Max ops per batch call (default 50).
        mode: "atomic" or "best_effort" per chunk (default "atomic").

    Returns:
        Flat list of all sub-op results in order.

    Raises:
        RuntimeError: if any chunk fails in atomic mode (partial progress is
            preserved from prior committed chunks).
    """
    from su_mcp_bridge.transport.ws_client import SketchUpWSClient

    if not ops:
        return []

    total = len(ops)
    n_chunks = math.ceil(total / chunk_size)
    all_results: list[Any] = []

    log.info("dispatch_in_chunks: %d ops → %d chunks of ≤%d", total, n_chunks, chunk_size)

    for i in range(n_chunks):
        chunk = ops[i * chunk_size : (i + 1) * chunk_size]
        timeout = SketchUpWSClient.batch_timeout(len(chunk))
        log.debug("chunk %d/%d: %d ops (timeout=%.1fs)", i + 1, n_chunks, len(chunk), timeout)

        result = client.send_request(
            "ops.batch",
            {"ops": chunk, "mode": mode},
            timeout=timeout,
        )

        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(
                f"Chunk {i + 1}/{n_chunks} failed at op "
                f"{i * chunk_size}–{i * chunk_size + len(chunk) - 1}: {result['error']}"
            )

        if isinstance(result, list):
            all_results.extend(result)
        else:
            all_results.append(result)

    log.info("dispatch_in_chunks: complete — %d results", len(all_results))
    return all_results


def index_entities_by_id(model: Any) -> dict[str, dict[str, Any]]:
    """Walk a BuildingModel and return {ai_id: dump_dict}.

    Used by `model.apply` to feed `changeset_to_ops` so modifications can
    look up the new field values.
    """
    out: dict[str, dict[str, Any]] = {}
    for m in getattr(model, "materials", []) or []:
        out[m.id] = m.model_dump()
    for layer in getattr(model, "layers", []) or []:
        out[layer.id] = layer.model_dump()
    for level in getattr(model, "levels", []) or []:
        out[level.id] = {"id": level.id, "name": level.name, "elevation_mm": level.elevation_mm}
        for w in level.walls:
            d = w.model_dump()
            d["level_id"] = level.id
            d["_type"] = "Wall"
            out[w.id] = d
        for o in level.openings:
            out[o.id] = o.model_dump()
        for s in level.slabs:
            d = s.model_dump()
            d["level_id"] = level.id
            out[s.id] = d
        for r in level.roofs:
            out[r.id] = r.model_dump()
        for c in level.columns:
            out[c.id] = c.model_dump()
        for b in level.beams:
            out[b.id] = b.model_dump()
        for c in level.components:
            out[c.id] = c.model_dump()
        for d in level.dimensions:
            out[d.id] = d.model_dump()
    for p in getattr(model, "primitives", []) or []:
        out[p.id] = p.model_dump()
    for p in getattr(model, "parametric", []) or []:
        out[p.id] = p.model_dump()
    return out
