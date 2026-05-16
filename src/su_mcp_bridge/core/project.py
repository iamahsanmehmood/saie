"""core/project.py — Per-project folder management.

Each project gets its own structured folder:
    projects/<name>/
        project.json        — Metadata
        model/              — .skp files
        captures/           — Screenshots
        reports/            — MD/CSV/JSON reports
        data/               — Scan snapshots, building models
        assets/             — Renders, walkthroughs
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .logger import get_logger

if TYPE_CHECKING:
    from .model import BuildingModel

log = get_logger(__name__)

_DEFAULT_BASE = os.path.join(os.path.expanduser("~"), "Documents", "SU_MCP_Projects")
_ACTIVE_FILE = os.path.join(os.path.expanduser("~"), ".su_mcp_active_project")
_active_project: ProjectContext | None = None


@dataclass
class ProjectContext:
    """Represents an active project with its folder structure."""

    name: str
    root: Path
    created: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def model_dir(self) -> Path:
        return self.root / "model"

    @property
    def captures_dir(self) -> Path:
        return self.root / "captures"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def assets_dir(self) -> Path:
        return self.root / "assets"

    @property
    def project_json(self) -> Path:
        return self.root / "project.json"

    def ensure_dirs(self) -> None:
        """Create all subdirectories if they don't exist."""
        for d in [
            self.model_dir,
            self.captures_dir,
            self.reports_dir,
            self.data_dir,
            self.data_dir / "scan_history",
            self.assets_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def save_metadata(self) -> Path:
        """Write project.json with current metadata."""
        self.metadata["name"] = self.name
        self.metadata["updated"] = datetime.now().isoformat()
        if not self.metadata.get("created"):
            self.metadata["created"] = self.created or datetime.now().isoformat()
        with open(self.project_json, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2, ensure_ascii=False)
        return self.project_json

    def save_capture(self, preset: str, source_path: str) -> Path:
        """Copy a capture image into the project's captures folder."""
        src = Path(source_path)
        idx = len(list(self.captures_dir.glob(f"{preset}_*"))) + 1
        dest = self.captures_dir / f"{preset}_{idx:03d}{src.suffix}"
        shutil.copy2(src, dest)
        log.info(f"Capture saved: {dest}")
        return dest

    def save_report(self, content: str, filename: str) -> Path:
        """Write a report file to the reports folder."""
        dest = self.reports_dir / filename
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content)
        log.info(f"Report saved: {dest}")
        return dest

    def save_snapshot(self, data: dict, label: str = "") -> Path:
        """Save a JSON data snapshot to the data folder."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"scan_{label}_{ts}.json" if label else f"scan_{ts}.json"
        dest = self.data_dir / "scan_history" / name
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info(f"Snapshot saved: {dest}")
        return dest

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "root": str(self.root),
            "created": self.created,
            "model_dir": str(self.model_dir),
            "captures_dir": str(self.captures_dir),
            "reports_dir": str(self.reports_dir),
            "data_dir": str(self.data_dir),
            "assets_dir": str(self.assets_dir),
        }


def create_project(name: str, base_dir: str = "") -> ProjectContext:
    """Create a new project with full folder structure."""
    base = Path(base_dir) if base_dir else Path(_DEFAULT_BASE)
    safe_name = name.replace(" ", "_").replace("/", "_")
    ts = datetime.now().strftime("%Y-%m-%d")
    folder_name = f"{safe_name}_{ts}"
    root = base / folder_name

    ctx = ProjectContext(
        name=name,
        root=root,
        created=datetime.now().isoformat(),
    )
    ctx.ensure_dirs()
    ctx.save_metadata()

    global _active_project
    _active_project = ctx
    with open(_ACTIVE_FILE, "w", encoding="utf-8") as f:
        f.write(str(root))

    log.info(f"Project created: {root}")
    return ctx


def list_projects(base_dir: str = "") -> list[dict[str, Any]]:
    """List all projects in the base directory."""
    base = Path(base_dir) if base_dir else Path(_DEFAULT_BASE)
    if not base.exists():
        return []

    projects = []
    for d in sorted(base.iterdir()):
        pj = d / "project.json"
        if pj.exists():
            try:
                with open(pj, encoding="utf-8") as f:
                    meta = json.load(f)
                projects.append(
                    {
                        "name": meta.get("name", d.name),
                        "path": str(d),
                        "created": meta.get("created", ""),
                        "updated": meta.get("updated", ""),
                    }
                )
            except Exception:
                projects.append({"name": d.name, "path": str(d), "created": "", "updated": ""})
    return projects


def open_project(name: str, base_dir: str = "") -> ProjectContext | None:
    """Open an existing project by name (fuzzy match on folder names)."""
    base = Path(base_dir) if base_dir else Path(_DEFAULT_BASE)
    if not base.exists():
        return None

    for d in base.iterdir():
        if name.lower().replace(" ", "_") in d.name.lower():
            pj = d / "project.json"
            meta = {}
            if pj.exists():
                with open(pj, encoding="utf-8") as f:
                    meta = json.load(f)

            ctx = ProjectContext(
                name=meta.get("name", d.name),
                root=d,
                created=meta.get("created", ""),
                metadata=meta,
            )
            global _active_project
            _active_project = ctx
            with open(_ACTIVE_FILE, "w", encoding="utf-8") as f:
                f.write(str(d))
            log.info(f"Project opened: {d}")
            return ctx
    return None


def get_active_project() -> ProjectContext | None:
    """Return the currently active project, or None."""
    global _active_project
    if _active_project is not None:
        return _active_project

    if os.path.exists(_ACTIVE_FILE):
        try:
            with open(_ACTIVE_FILE, encoding="utf-8") as f:
                path = f.read().strip()
            if os.path.exists(path):
                # Load context directly from path
                pj = Path(path) / "project.json"
                meta = {}
                if pj.exists():
                    with open(pj, encoding="utf-8") as f:
                        meta = json.load(f)
                _active_project = ProjectContext(
                    name=meta.get("name", Path(path).name),
                    root=Path(path),
                    created=meta.get("created", ""),
                    metadata=meta,
                )
                return _active_project
        except Exception as e:
            log.warning(f"Failed to load active project: {e}")
    return None


def set_active_project(ctx: ProjectContext | None) -> None:
    """Set the active project context."""
    global _active_project
    _active_project = ctx
    if ctx:
        with open(_ACTIVE_FILE, "w", encoding="utf-8") as f:
            f.write(str(ctx.root))
    elif os.path.exists(_ACTIVE_FILE):
        os.remove(_ACTIVE_FILE)


# ---------------------------------------------------------------------------
# Project — file-locked project with BuildingModel versioning
# ---------------------------------------------------------------------------


class ProjectLockError(Exception):
    pass


class Project:
    """Structured project folder with file-based locking, model versioning, and snapshots."""

    _LOCK_FILE = ".lock"
    _BUILDING_FILE = "building.json"
    _MANIFEST_FILE = "project.json"
    _DIRS = [
        "snapshots",
        "history",
        "history/building_versions",
        "captures/views",
        "captures/ad_hoc",
        "exports",
        "logs",
    ]

    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock_path = root / self._LOCK_FILE

    def __enter__(self) -> Project:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        if self._lock_path.exists():
            self._lock_path.unlink(missing_ok=True)

    def _acquire_lock(self) -> None:
        if self._lock_path.exists():
            raise ProjectLockError(f"Project already open: {self._root}")
        self._lock_path.write_text("locked", encoding="utf-8")

    @classmethod
    def create(cls, root: Path | str, model: BuildingModel) -> Project:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        for d in cls._DIRS:
            (root / d).mkdir(parents=True, exist_ok=True)
        p = cls(root)
        p._acquire_lock()
        p.save_model(model, _initial=True)
        return p

    @classmethod
    def open(cls, root: Path | str) -> Project:
        root = Path(root)
        if not root.exists():
            raise FileNotFoundError(f"Project not found: {root}")
        p = cls(root)
        p._acquire_lock()
        return p

    def load_model(self) -> BuildingModel:
        from .model import BuildingModel as _BM

        data = json.loads((self._root / self._BUILDING_FILE).read_text(encoding="utf-8"))
        return _BM.model_validate(data)

    def save_model(self, model: BuildingModel, _initial: bool = False) -> str:
        import hashlib

        text = json.dumps(model.model_dump(), indent=2, ensure_ascii=False, sort_keys=True)
        sha1 = hashlib.sha1(text.encode()).hexdigest()

        building_path = self._root / self._BUILDING_FILE
        if not _initial and building_path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            ver = self._root / "history" / "building_versions" / f"building.{ts}.json"
            shutil.copy2(building_path, ver)

        building_path.write_text(text, encoding="utf-8")

        manifest: dict[str, Any] = {}
        manifest_path = self._root / self._MANIFEST_FILE
        if manifest_path.exists():
            with contextlib.suppress(Exception):
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["name"] = model.project.name
        manifest["model_hash"] = sha1
        manifest["updated"] = datetime.now().isoformat()
        manifest.setdefault("created", manifest["updated"])
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return sha1

    def save_snapshot(self, name: str) -> Path:
        dest = self._root / "snapshots" / f"{name}.json"
        shutil.copy2(self._root / self._BUILDING_FILE, dest)
        return dest

    def list_snapshots(self) -> list[str]:
        return sorted(s.name for s in (self._root / "snapshots").glob("*.json"))

    def restore_snapshot(self, name: str) -> BuildingModel:
        from .model import BuildingModel as _BM

        snap = self._root / "snapshots" / name
        if not snap.exists():
            raise FileNotFoundError(f"Snapshot not found: {name}")
        return _BM.model_validate(json.loads(snap.read_text(encoding="utf-8")))

    def append_memory(self, note: str) -> None:
        mem = self._root / "logs" / "memory.md"
        with open(mem, "a", encoding="utf-8") as f:
            f.write(f"{note}\n")

    def read_memory(self) -> str:
        mem = self._root / "logs" / "memory.md"
        return mem.read_text(encoding="utf-8") if mem.exists() else ""


def empty_model(name: str) -> BuildingModel:
    from .model import BuildingModel as _BM
    from .model import ProjectMeta as _PM

    return _BM(project=_PM(name=name, display_units="mm"), levels=[])
