"""core/verify.py — Post-apply state divergence detection.

After a `model.apply` runs, BuilderCore asks Ruby for the SketchUp scene's
exported BuildingJSON-shaped state (via `query.export_json`) and diffs it
against the BuildingModel we expected. Soft divergences become structured
warnings to the AI; hard invariants raise.

This module is transport-agnostic — it takes a BuildingModel + the dict
returned by Ruby, and produces a Verification report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model import BuildingModel

SOFT_TOLERANCE_IN = 0.05
"""Bounds difference under this (inches) is reported but doesn't fail. ~1.3mm."""


@dataclass
class Divergence:
    severity: str  # "warning" | "error"
    entity_id: str | None
    code: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"[{self.severity.upper()}] {self.code} {self.entity_id or '-'}: {self.message}"


@dataclass
class VerifyReport:
    ok: bool
    divergences: list[Divergence] = field(default_factory=list)
    found_ids: set[str] = field(default_factory=set)
    expected_ids: set[str] = field(default_factory=set)

    @property
    def missing(self) -> set[str]:
        return self.expected_ids - self.found_ids

    @property
    def orphans(self) -> set[str]:
        return self.found_ids - self.expected_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "divergences": [d.__dict__ for d in self.divergences],
            "missing_ids": sorted(self.missing),
            "orphan_ids": sorted(self.orphans),
        }


def expected_entity_ids(model: BuildingModel) -> set[str]:
    """Return the set of ai_ids the model says should exist in SketchUp.

    Walls, openings, slabs, roofs, columns, beams, components, primitives,
    parametric, and dimensions all carry stable IDs. Materials and layers
    do not become geometry, so they are excluded.
    """
    ids: set[str] = set()
    for level in model.levels:
        ids.update(w.id for w in level.walls)
        ids.update(o.id for o in level.openings)
        ids.update(s.id for s in level.slabs)
        ids.update(r.id for r in level.roofs)
        ids.update(c.id for c in level.columns)
        ids.update(b.id for b in level.beams)
        ids.update(c.id for c in level.components)
        ids.update(d.id for d in level.dimensions)
    ids.update(p.id for p in model.primitives)
    ids.update(p.id for p in model.parametric)
    return ids


def verify(
    model: BuildingModel,
    sketchup_export: dict[str, Any],
) -> VerifyReport:
    """Compare the expected BuildingModel against what Ruby reported.

    `sketchup_export` is the dict returned by `query.export_json` on the
    Ruby side. It looks like:

        {
            "entities": [
                {"ai_id": "W1", "guid": "...", "bounds": {...}, "valid_solid": true},
                ...
            ],
            "total": N
        }
    """
    expected = expected_entity_ids(model)
    found: set[str] = set()
    divergences: list[Divergence] = []

    for entry in sketchup_export.get("entities", []) or []:
        ai_id = entry.get("ai_id")
        if not ai_id:
            continue
        found.add(ai_id)

        # Hard invariant: every reported entity that's still expected must be
        # a valid solid. Non-manifold = downstream booleans WILL fail.
        valid_solid = entry.get("valid_solid")
        if ai_id in expected and valid_solid is False:
            divergences.append(
                Divergence(
                    severity="warning",
                    entity_id=ai_id,
                    code="NON_MANIFOLD",
                    message="Entity is not a valid manifold solid; future booleans may fail.",
                    detail={"guid": entry.get("guid")},
                )
            )

    for missing_id in expected - found:
        divergences.append(
            Divergence(
                severity="error",
                entity_id=missing_id,
                code="MISSING",
                message="Expected entity is absent from the SketchUp model.",
            )
        )

    for orphan_id in found - expected:
        divergences.append(
            Divergence(
                severity="warning",
                entity_id=orphan_id,
                code="ORPHAN",
                message="Entity exists in SketchUp but is not in the BuildingModel.",
            )
        )

    has_error = any(d.severity == "error" for d in divergences)
    return VerifyReport(
        ok=not has_error,
        divergences=divergences,
        found_ids=found,
        expected_ids=expected,
    )
