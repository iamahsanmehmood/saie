# SketchUp MCP Pipeline Limitations & Issues

During the development of the programmatic 35x50 house generation pipeline, the following limitations and issues were identified with the SketchUp MCP Bridge:

### 1. Model Clearing Crashes (`ops.clear_model`)
Sending `ops.clear_model` over the WebSocket connection when the model is very large or complex occasionally causes SketchUp to freeze or the WebSocket connection to drop (`[WinError 10054] An existing connection was forcibly closed`). 
**Workaround:** Avoid programmatic clearing for heavy scenes, and instead manually restart SketchUp with a clean template using `sb sketchup restart`.

### 2. Component Definition Caching
SketchUp tightly caches `ComponentDefinition` objects based on their name. If a window or door is created programmatically, its dimensions and hole-cutting properties are locked to that name. If the script attempts to create a window with the *same name* but *different dimensions*, SketchUp silently re-uses the old cached geometry.
**Workaround:** Enforce globally unique component naming (e.g., appending a UUID or strict version prefix like `AI_RECIPE_V3_`) to ensure fresh geometry is baked for every size variation.

### 3. ~~Lack of Native "Glue-to-Face" over API~~ ✅ RESOLVED
Previously, `ops.opening.cut` cut a hole and then a separate `ops.component.place` call tried to place a frame using absolute 3D coordinates — causing systematic misalignment. 
**Fix (Solution B):** `ops.opening.cut` now accepts an optional `generate_frame` parameter (`"door"` or `"window"`). When set, the Ruby handler builds the frame geometry *inside the wall's own local coordinate system* using the exact same transform as the boolean cutter, mathematically guaranteeing zero misalignment. No more floating doors or clashing windows.

### 4. WebSocket Port Discovery
If multiple SketchUp instances are running or one crashes ungracefully, the bridge will increment its port (e.g., `9876` -> `9877`). Command-line scripts like `sb render` might auto-discover a different port than the building script, causing "Model is empty" errors.
**Workaround:** Hardcode the connection port explicitly in Python scripts (e.g., `client = SketchUpWSClient(port=9876)`) and manually kill orphaned `SketchUp.exe` processes.

### 5. Boolean Subtract Reliability (Known SketchUp Limitation)
SketchUp's `group.subtract(other_group)` boolean operation is inherently fragile. It requires both groups to be clean manifold solids. After the first boolean subtract modifies a wall group, subsequent boolean operations on the SAME wall may produce:
- Silent failures (no hole is cut)
- Corrupted geometry (torn faces, non-manifold edges)
- "Boolean subtract returned nil" errors

This is a **SketchUp engine limitation**, not a bridge bug. The SketchUp team acknowledges that the Solid Tools API is unreliable for programmatic workflows.

**Current Status:** Doors and windows that are the first/only cut on a wall work reliably. Multiple sequential cuts on the same wall degrade progressively.

**Future Fix Options:**
- Use native SketchUp "cutting components" (glue-to-face components with cutting boundaries) instead of boolean subtract
- Pre-compute all openings for a wall and cut them in a single boolean operation
- Use direct face-editing (delete faces, redraw edges) instead of boolean subtract entirely
