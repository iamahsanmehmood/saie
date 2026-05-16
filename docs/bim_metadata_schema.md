# SAIE BIM Metadata Schema (v1.0)

This document defines the standard attribute dictionary that SAIE writes and reads on SketchUp entities to enable structural analysis, quantity takeoff, BIM interoperability, and external reporting.

---

## The `"bim"` Dictionary

Every SAIE entity *may* carry a `"bim"` attribute dictionary. Nothing enforces its presence — absence means the attribute is unset, not an error. Read via `query.attr.get`, write via `ops.attr.set` or `ops.attr.set_bulk`.

```
entity.attribute_dictionary("bim")
  └── structural_role    → string
  └── material_spec      → string
  └── fire_rating        → string
  └── thermal_resistance → number (m²K/W)
  └── ifc_class          → string
  └── cost_per_unit      → number
  └── quantity_basis     → string
  └── load_kpa           → number (kPa)
  └── notes              → string
```

---

## Key Reference

### `structural_role`
**Type:** string  
**Purpose:** Structural classification used in Ansys masking, load-path tracing, and LGS detailing.

| Value | Meaning |
|-------|---------|
| `"load_bearing"` | Transfers vertical and/or lateral loads to foundation |
| `"non_load_bearing"` | Carries self-weight only |
| `"partition"` | Interior divider, no structural role |
| `"shear_wall"` | Lateral-load-resisting element |
| `"retaining"` | Earth-retaining element |
| `"column"` | Vertical point-load element |
| `"beam"` | Horizontal span element |

---

### `material_spec`
**Type:** string  
**Purpose:** Engineering material identifier for structural and thermal analysis. Use the format `<type>_<grade>` where applicable.

| Example | Meaning |
|---------|---------|
| `"concrete_C30"` | Normal-weight concrete, 30 MPa |
| `"concrete_C20"` | Normal-weight concrete, 20 MPa |
| `"masonry_clay"` | Clay brick masonry |
| `"masonry_block"` | Concrete block masonry |
| `"timber_LVL"` | Laminated Veneer Lumber |
| `"steel_S275"` | Structural steel grade S275 |
| `"lgs_G550"` | Light gauge steel, 550 MPa |
| `"glass_DGU"` | Double-glazed unit |
| `"gypsum_board"` | Standard plasterboard |

---

### `fire_rating`
**Type:** string  
**Purpose:** Fire resistance period for code compliance reporting.

| Value | Meaning |
|-------|---------|
| `"30min"` | 30-minute fire resistance |
| `"60min"` | 60-minute fire resistance |
| `"90min"` | 90-minute fire resistance |
| `"120min"` | 2-hour fire resistance |
| `"none"` | No rating required |

---

### `thermal_resistance`
**Type:** number (m²K/W)  
**Purpose:** R-value for energy modeling and compliance calculations. Store as a float.

```
Example: 2.5   → R-value of 2.5 m²K/W
```

---

### `ifc_class`
**Type:** string  
**Purpose:** IFC 4.x class mapping for BIM interoperability and export. Enables downstream tools (Revit, BIMx, Navisworks) to correctly classify entities imported from SAIE models.

| SAIE Entity | Recommended IFC class |
|-------------|----------------------|
| wall | `"IfcWall"` |
| wall (curtain) | `"IfcCurtainWall"` |
| slab (floor) | `"IfcSlab"` |
| slab (roof) | `"IfcRoof"` |
| opening (door) | `"IfcDoor"` |
| opening (window) | `"IfcWindow"` |
| column | `"IfcColumn"` |
| beam | `"IfcBeam"` |
| stair | `"IfcStair"` |
| space | `"IfcSpace"` |

---

### `cost_per_unit`
**Type:** number  
**Purpose:** Unit cost for quantity takeoff and BOM generation. Currency is project-defined (see project.json).

```
Example: 120.50  → 120.50 [currency] per quantity_basis unit
```

---

### `quantity_basis`
**Type:** string  
**Purpose:** The unit used to measure this entity for quantity takeoff. Paired with `cost_per_unit`.

| Value | Meaning |
|-------|---------|
| `"m2"` | Square metres (area) — walls, slabs, cladding |
| `"m3"` | Cubic metres (volume) — concrete, fill |
| `"lm"` | Linear metre — beams, lintels, framing |
| `"nr"` | Number (count) — doors, windows, columns |
| `"kg"` | Kilograms — steel, fixings |
| `"tonne"` | Tonnes — bulk materials |

---

### `load_kpa`
**Type:** number (kPa)  
**Purpose:** Design load in kiloPascals for structural analysis and Ansys export masking.

```
Example: 2.0   → 2.0 kPa imposed load (residential floor)
         5.0   → 5.0 kPa (office floor)
         0.75  → 0.75 kPa (roof, snow-free)
```

---

### `notes`
**Type:** string  
**Purpose:** Free-text annotation for any remarks that don't fit a structured field. Included in report output.

---

## Usage Examples

### Tag a wall as load-bearing with a fire rating

```json
{
  "method": "ops.attr.set_bulk",
  "params": {
    "operations": [
      {"ai_id": "W1", "dict_name": "bim", "key": "structural_role", "value": "load_bearing"},
      {"ai_id": "W1", "dict_name": "bim", "key": "material_spec",   "value": "masonry_clay"},
      {"ai_id": "W1", "dict_name": "bim", "key": "fire_rating",     "value": "60min"},
      {"ai_id": "W1", "dict_name": "bim", "key": "ifc_class",       "value": "IfcWall"},
      {"ai_id": "W1", "dict_name": "bim", "key": "cost_per_unit",   "value": 85.0},
      {"ai_id": "W1", "dict_name": "bim", "key": "quantity_basis",  "value": "m2"}
    ]
  }
}
```

### Query all load-bearing walls

```json
{
  "method": "query.attr.find",
  "params": {
    "dict_name": "bim",
    "key": "structural_role",
    "value": "load_bearing",
    "type": "wall"
  }
}
```

### Read a full BIM record for one entity

```json
{
  "method": "query.attr.get",
  "params": {
    "ai_id": "W1",
    "dict_name": "bim"
  }
}
```

**Response:**
```json
{
  "ai_id": "W1",
  "dict_name": "bim",
  "data": {
    "structural_role": "load_bearing",
    "material_spec":   "masonry_clay",
    "fire_rating":     "60min",
    "ifc_class":       "IfcWall",
    "cost_per_unit":   85.0,
    "quantity_basis":  "m2"
  }
}
```

---

## Integration with Reports

When `generate_report` runs, it reads the `"bim"` dictionary from every entity and includes a **BIM Data** section in the Markdown output and a dedicated `bim_attributes` column group in the CSV export. Entities with no `"bim"` dictionary are reported as `—` in those columns.

---

## Extension Rules

- **Namespace your own keys.** If you need project-specific keys, prefix them: `"project_zone"`, `"client_ref"`. Never write into the `"su_mcp_bridge"` dictionary — that is reserved for SAIE internal state.
- **Values are always scalars.** SketchUp attribute dictionaries store strings, numbers, and booleans. Do not store arrays or nested objects — flatten them into multiple keys (`"load_dead_kpa"`, `"load_live_kpa"`) or serialize to a JSON string.
- **Dictionary name is case-sensitive.** Always use lowercase `"bim"`. `"BIM"` and `"Bim"` are separate dictionaries.
