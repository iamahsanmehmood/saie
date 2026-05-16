# House Generator Geometry & Placement Issues

This document outlines the critical geometric alignment and boolean operation issues currently present in the `HouseGenerator` pipeline (v1.0.0).

## Core Problem
The system attempts to build walls, cut boolean openings, and insert 3D components (doors/windows) as three separate mathematical steps. While the walls and holes are aligning correctly, the 3D components (frames and door panels) are failing to align with the holes, resulting in floating objects, wall clashes, and missing geometry.

## Detailed Issue Breakdown

### 1. Component vs. Cut Misalignment
- **The Symptom**: The user reports "those are not created by cut but additional floating clashing with walls."
- **The Cause**: `ops.opening.cut` calculates the hole position based on a 1D offset along the wall's local centerline (from its lexicographical origin). However, `ops.component.place` uses absolute global 3D coordinates `[x, y, z]` and global rotations.
- **The Result**: The math used to convert the 1D offset into absolute global coordinates for the component is flawed. The components end up shifted away from the boolean hole. Because the component is solid and not in the hole, it intersects raw wall geometry, causing Z-fighting and clashing.

### 2. Component Bounding Box Rotation Errors
- **The Symptom**: "All window doors are outside."
- **The Cause**: The components (windows/doors) are built natively in SketchUp from `[0, 0, 0]` to `[width, thickness, height]`. When we place them on the Back, Left, or Right walls, we apply a rotation (90, 180, 270 degrees).
- **The Result**: Rotating a bounding box around its `[0,0,0]` insertion point causes it to swing into a different coordinate quadrant. For example, a 180-degree rotation shifts the geometry by `-width` and `-thickness`. While we attempted to compensate for this in Python by adding offsets, the mathematical conversion is incorrect, causing components to literally stick out of the building.

### 3. Missing or Misaligned Doors
- **The Symptom**: "No main entrance door" and interior doors are wrong.
- **The Cause**: In `component.rb`, the door recipe creates a simple panel and applies a native 60-degree rotation to simulate an open door. 
- **The Result**: 
  - When placed at `Y = t/2` (the centerline of the front wall), the 60-degree rotation causes the panel to intersect the solid wall structure, hiding it completely (hence "no main entrance door").
  - Interior doors were placed at the wall boundary but parallel to the partition, making them look like solid blocks stuck to the wall rather than open panels.

### 4. Cache Persistence Bug
- **The Symptom**: Old, broken component designs were stubbornly persisting across runs (e.g., solid blocks instead of hollow windows).
- **The Cause**: SketchUp caches `Sketchup::ComponentDefinition` by name. Even if `clear_model` deletes all instances, the definition remains in the cache. 
- **The Status**: *Partially mitigated* by appending `V3_` to the recipe names, but future iterations must ensure that if a recipe's internal logic changes, its definition name is also bumped, or `model.definitions.purge_unused` is properly called.

## Proposed Architectural Solutions

To definitively solve this, we must abandon the dual-system (cutting holes + placing components via absolute math) in favor of a unified approach.

### Solution A: Unified Component Cutting (The SketchUp Way)
Instead of cutting a hole and trying to place a component inside it, we should utilize native SketchUp "cutting components":
1. Define the window/door component such that its origin is on the gluing face, and give it a cutting boundary.
2. In Ruby, glue the component directly to the wall face.
3. **Benefit**: SketchUp handles the boolean hole automatically, and the component is guaranteed to be perfectly aligned with the hole.

### Solution B: Procedural Generation (The Math Way)
If we must use pure code:
1. Do not place separate components.
2. When calling `ops.opening.cut`, augment the Ruby script to automatically draw the frame geometry *inside the local coordinate space of the wall* immediately after executing the boolean subtraction.
3. **Benefit**: The frame is built using the exact same local coordinates as the hole, mathematically guaranteeing zero misalignment.

## Next Steps for Developers
1. Roll back `_place_window` and `_place_door` absolute coordinate math.
2. Investigate implementing "Solution B", where `ops.opening.cut` takes an optional parameter `generate_frame: true` and handles the geometry internally within `opening.rb`.
