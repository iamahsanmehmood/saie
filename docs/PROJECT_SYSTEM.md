# Project System

SU MCP Bridge includes a per-project folder management system that automatically organizes all project-related files.

## Quick Start

```bash
# Create a project
sb project create "My House"

# All subsequent captures, reports, and scans are auto-routed to this project

# List all projects
sb project list

# Switch projects
sb project open "Other Project"

# Check active project
sb project info
```

## Folder Structure

When you create a project, the following folder structure is automatically created:

```
~/Documents/SU_MCP_Projects/
└── My_House_2026-05-04/
    ├── project.json              # Metadata (name, timestamps)
    ├── model/                    # SketchUp .skp files
    ├── captures/                 # Screenshots and view captures
    │   ├── iso_001.png
    │   ├── plan_001.png
    │   └── ...
    ├── reports/                  # Generated reports
    │   ├── model_report_20260504_153000.md
    │   ├── inventory_20260504_153000.csv
    │   └── clash_report.md
    ├── data/                     # Raw data
    │   └── scan_history/         # Timestamped scan snapshots
    │       ├── scan_20260504_150000.json
    │       └── scan_20260504_160000.json
    └── assets/                   # Final outputs
        ├── walkthrough.mp4       # Walkthrough videos
        └── render_iso.png        # HQ renders
```

## project.json

Each project has a metadata file:

```json
{
  "name": "My House",
  "created": "2026-05-04T15:30:00",
  "updated": "2026-05-04T16:45:00"
}
```

## Auto-routing

When a project is active:
- **Reports** (`sb report`) → `project/reports/`
- **Scans** (`sb scan` with JSON export) → `project/data/scan_history/`
- **Captures** → `project/captures/` (via `ProjectContext.save_capture()`)

## Python API

```python
from su_mcp_bridge.core.project import create_project, open_project, get_active_project

# Create
ctx = create_project("My House")
print(ctx.reports_dir)  # Path to reports folder

# Use
ctx.save_report(content, "model_report.md")
ctx.save_capture("iso", "/path/to/capture.png")
ctx.save_snapshot(scan_data, label="initial")

# Switch
ctx = open_project("Other House")

# Check
active = get_active_project()
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `create_project(name, base_dir?)` | Create new project |
| `list_all_projects(base_dir?)` | List all projects |
| `set_active_project(name, base_dir?)` | Open and activate project |

## Default Location

Projects are stored in `~/Documents/SU_MCP_Projects/` by default. Override with the `base_dir` parameter on any command.
