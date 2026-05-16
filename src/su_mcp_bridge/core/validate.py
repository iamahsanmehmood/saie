from .model import BuildingModel


class ValidationError(Exception):
    pass


class ValidationIssue:
    def __init__(self, entity_id: str, message: str, level: str = "error"):
        self.entity_id = entity_id
        self.message = message
        self.level = level  # "error" or "warning"

    def __repr__(self):
        return f"[{self.level.upper()}] {self.entity_id}: {self.message}"


def validate_model(model: BuildingModel) -> list[ValidationIssue]:
    """
    Validates a BuildingModel for semantic correctness.
    Returns a list of ValidationIssue objects.
    """
    issues = []

    # 1. Collect all valid IDs for reference checking
    valid_material_ids = {m.id for m in model.materials}
    valid_layer_ids = {lvl.id for lvl in model.layers}
    {lvl.id for lvl in model.levels}

    # Check uniqueness of IDs globally
    all_ids = set()

    def check_id(entity_id: str):
        if entity_id in all_ids:
            issues.append(ValidationIssue(entity_id, "Duplicate ID found in project."))
        all_ids.add(entity_id)

    # Validate materials, layers, levels
    for m in model.materials:
        check_id(m.id)
    for lvl in model.layers:
        check_id(lvl.id)
    for lvl in model.levels:
        check_id(lvl.id)

    # Collect valid wall IDs across all levels
    valid_wall_ids = {w.id for lvl in model.levels for w in lvl.walls}

    for level in model.levels:
        # Validate Walls
        for wall in level.walls:
            check_id(wall.id)
            if wall.level_id != level.id:
                issues.append(
                    ValidationIssue(
                        wall.id,
                        f"Wall level_id '{wall.level_id}' does not match its parent level '{level.id}'.",
                    )
                )
            if wall.material_id_exterior and wall.material_id_exterior not in valid_material_ids:
                issues.append(
                    ValidationIssue(
                        wall.id, f"Invalid material_id_exterior: {wall.material_id_exterior}"
                    )
                )
            if wall.material_id_interior and wall.material_id_interior not in valid_material_ids:
                issues.append(
                    ValidationIssue(
                        wall.id, f"Invalid material_id_interior: {wall.material_id_interior}"
                    )
                )
            if wall.layer_id and wall.layer_id not in valid_layer_ids:
                issues.append(ValidationIssue(wall.id, f"Invalid layer_id: {wall.layer_id}"))

            # Wall length check
            if len(wall.centerline) == 2:
                dx = wall.centerline[1][0] - wall.centerline[0][0]
                dy = wall.centerline[1][1] - wall.centerline[0][1]
                length = (dx * dx + dy * dy) ** 0.5
                if length < 1.0:
                    issues.append(
                        ValidationIssue(wall.id, "Wall centerline length is less than 1mm.")
                    )
            else:
                issues.append(
                    ValidationIssue(wall.id, "Wall centerline must have exactly 2 points.")
                )

        # Validate Openings
        for op in level.openings:
            check_id(op.id)
            if op.wall_id not in valid_wall_ids:
                issues.append(
                    ValidationIssue(op.id, f"Opening references non-existent wall_id: {op.wall_id}")
                )

            # Find the wall to check constraints
            wall = next((w for w in level.walls if w.id == op.wall_id), None)
            if wall:
                dx = wall.centerline[1][0] - wall.centerline[0][0]
                dy = wall.centerline[1][1] - wall.centerline[0][1]
                length = (dx * dx + dy * dy) ** 0.5

                if op.offset_mm < 0:
                    issues.append(ValidationIssue(op.id, "Opening offset cannot be negative."))
                if op.offset_mm + op.width_mm > length:
                    issues.append(
                        ValidationIssue(
                            op.id,
                            f"Opening offset ({op.offset_mm}) + width ({op.width_mm}) exceeds wall length ({length:.2f}).",
                        )
                    )
                if op.sill_mm + op.height_mm > wall.height_mm:
                    issues.append(
                        ValidationIssue(
                            op.id,
                            f"Opening sill ({op.sill_mm}) + height ({op.height_mm}) exceeds wall height ({wall.height_mm}).",
                        )
                    )

        # Other entities...
        for slab in level.slabs:
            check_id(slab.id)
            if len(slab.polygon) < 3:
                issues.append(ValidationIssue(slab.id, "Slab polygon must have at least 3 points."))

    return issues
