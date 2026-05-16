"""
SAIE central configuration loader.

Single source of truth for ports, paths, and feature flags. Used by:
  • The Python MCP server (`saie.mcp_server.server`)
  • The Python CLI (`saie` / `sb`)
  • The Python WS client (`su_mcp_bridge.transport.ws_client`)

The Ruby plugin has its own loader at `ruby_plugin/su_mcp_bridge/config.rb`
that follows the SAME resolution order so both sides agree on ports/paths
without manual sync.

Resolution order (first hit wins):
    1. $SAIE_CONFIG env var (absolute path)
    2. ./saie.toml in CWD
    3. ~/.saie/saie.toml
    4. <repo-root>/saie.toml (bundled default)

Any setting can be overridden by an environment variable using the pattern
SAIE_<SECTION>_<KEY> (uppercase, dot-separated keys become double-underscore).
For example:
    SAIE_BRIDGE_PORT=9999           overrides [bridge].port
    SAIE_STREAM_FPS=12              overrides [stream].fps
    SAIE_AGENTS_DEFAULT_PROVIDER=ollama
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

# Python 3.11+ ships tomllib in stdlib; fall back to tomli for 3.10.
if sys.version_info >= (3, 11):
    import tomllib  # type: ignore[import-not-found]
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]


# ─── Dataclass schema ─────────────────────────────────────────────────────────


@dataclass
class BridgeConfig:
    host: str = "127.0.0.1"
    port: int = 9876
    port_range: int = 10
    port_file: str = "~/.saie_port"
    timeout: float = 30.0


@dataclass
class StreamConfig:
    enabled: bool = True
    port: int = 9877
    port_range: int = 10
    source: str = "window"
    fps: int = 5
    quality: int = 70
    width: int = 800
    height: int = 600
    cache_ms: int = 100


@dataclass
class SketchUpConfig:
    version: str = "2025"
    install_path: str = ""
    plugins_path: str = ""
    autostart_bridge: bool = True


@dataclass
class ProjectsConfig:
    root: str = "~/Documents/SAIE_Projects"
    subdirs: list[str] = field(
        default_factory=lambda: [
            "model",
            "captures",
            "reports",
            "data/scan_history",
            "assets",
        ]
    )


@dataclass
class CaptureConfig:
    default_preset: str = "iso"
    default_resolution: str = "med"
    default_style: str = "default"
    isolation_margin: float = 0.15


@dataclass
class AgentsConfig:
    default_provider: str = "anthropic"
    default_anthropic_model: str = "claude-sonnet-4-5-20250929"
    default_ollama_model: str = "gemma3:4b"
    ollama_host: str = "http://localhost:11434"


@dataclass
class LoggingConfig:
    level: str = "info"
    ring_buffer_size: int = 500
    file: str = ""


@dataclass
class SecurityConfig:
    localhost_only: bool = True
    auth_token: str = ""


@dataclass
class ExperimentalConfig:
    enable_raw_ruby_exec: bool = True
    enable_walkthrough_video: bool = True
    enable_dxf_import: bool = True


@dataclass
class SaieConfig:
    """Resolved SAIE configuration. Pass around; never mutate after loading."""

    bridge: BridgeConfig = field(default_factory=BridgeConfig)
    stream: StreamConfig = field(default_factory=StreamConfig)
    sketchup: SketchUpConfig = field(default_factory=SketchUpConfig)
    projects: ProjectsConfig = field(default_factory=ProjectsConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    experimental: ExperimentalConfig = field(default_factory=ExperimentalConfig)

    # Provenance — useful for `saie config` to show where each value came from.
    source_path: str = "<defaults>"

    # ── Path helpers ──────────────────────────────────────────────────────────

    def port_file_path(self) -> Path:
        """Expanded path to the bridge port file."""
        return Path(self.bridge.port_file).expanduser()

    def projects_root_path(self) -> Path:
        return Path(self.projects.root).expanduser()

    def resolved_plugins_path(self) -> Path | None:
        """Where the SketchUp plugin should be installed.

        If `sketchup.plugins_path` is set explicitly, use it. Otherwise derive
        from `sketchup.version` using the platform default. Returns None on
        unsupported platforms.
        """
        if self.sketchup.plugins_path:
            return Path(self.sketchup.plugins_path).expanduser()

        version = self.sketchup.version
        if sys.platform == "win32":
            appdata = os.environ.get("APPDATA")
            if not appdata:
                return None
            return Path(appdata) / "SketchUp" / f"SketchUp {version}" / "SketchUp" / "Plugins"
        if sys.platform == "darwin":
            return (
                Path.home() / "Library" / "Application Support" / "SketchUp "
                f"{version}" / "SketchUp" / "Plugins"
            )
        return None  # Linux: no native SketchUp


# ─── Loader ───────────────────────────────────────────────────────────────────


def _candidate_paths() -> list[Path]:
    """Return config-file candidates in resolution order."""
    out: list[Path] = []
    env_override = os.environ.get("SAIE_CONFIG")
    if env_override:
        out.append(Path(env_override).expanduser())
    out.append(Path.cwd() / "saie.toml")
    out.append(Path.home() / ".saie" / "saie.toml")
    # Repo-bundled default — relative to this file
    out.append(Path(__file__).resolve().parents[3] / "saie.toml")
    return out


def _apply_table(target: Any, table: Mapping[str, Any]) -> None:
    """Copy known fields from a TOML mapping onto a dataclass instance.

    Unknown keys are silently ignored — old configs stay forward-compatible.
    """
    valid = {f.name for f in fields(target)}
    for key, value in table.items():
        if key in valid:
            setattr(target, key, value)


def _apply_env_overrides(cfg: SaieConfig) -> None:
    """Override any field with SAIE_<SECTION>_<KEY> environment variables."""
    sections: dict[str, Any] = {
        "bridge": cfg.bridge,
        "stream": cfg.stream,
        "sketchup": cfg.sketchup,
        "projects": cfg.projects,
        "capture": cfg.capture,
        "agents": cfg.agents,
        "logging": cfg.logging,
        "security": cfg.security,
        "experimental": cfg.experimental,
    }
    for section_name, dc in sections.items():
        for f in fields(dc):
            env_key = f"SAIE_{section_name.upper()}_{f.name.upper()}"
            raw = os.environ.get(env_key)
            if raw is None:
                continue
            current = getattr(dc, f.name)
            try:
                if isinstance(current, bool):
                    coerced: Any = raw.strip().lower() in ("1", "true", "yes", "on")
                elif isinstance(current, int):
                    coerced = int(raw)
                elif isinstance(current, float):
                    coerced = float(raw)
                elif isinstance(current, list):
                    # Comma-separated env override for list fields
                    coerced = [s.strip() for s in raw.split(",") if s.strip()]
                else:
                    coerced = raw
            except ValueError:
                # Skip silently — keep the file value
                continue
            setattr(dc, f.name, coerced)


def load_config(path: str | Path | None = None) -> SaieConfig:
    """Load the SAIE config from disk (or defaults if none found).

    Args:
        path: explicit path to a TOML file. Overrides the search order.
    """
    cfg = SaieConfig()

    candidates = [Path(path).expanduser()] if path else _candidate_paths()
    chosen: Path | None = None
    for p in candidates:
        if p.is_file():
            chosen = p
            break

    if chosen is not None:
        with chosen.open("rb") as f:
            data = tomllib.load(f)
        _apply_table(cfg.bridge, data.get("bridge", {}))
        _apply_table(cfg.stream, data.get("stream", {}))
        _apply_table(cfg.sketchup, data.get("sketchup", {}))
        _apply_table(cfg.projects, data.get("projects", {}))
        _apply_table(cfg.capture, data.get("capture", {}))
        _apply_table(cfg.agents, data.get("agents", {}))
        _apply_table(cfg.logging, data.get("logging", {}))
        _apply_table(cfg.security, data.get("security", {}))
        _apply_table(cfg.experimental, data.get("experimental", {}))
        cfg.source_path = str(chosen)

    _apply_env_overrides(cfg)
    return cfg


# ─── Module-level singleton ───────────────────────────────────────────────────

_CACHED: SaieConfig | None = None


def get_config(reload: bool = False) -> SaieConfig:
    """Return a process-wide cached SaieConfig.

    Call with reload=True to force a re-read (useful in tests or after the user
    edits saie.toml at runtime).
    """
    global _CACHED
    if _CACHED is None or reload:
        _CACHED = load_config()
    return _CACHED
