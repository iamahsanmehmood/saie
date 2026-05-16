"""core/logger.py — Centralized logging.

Replaces scattered `print()` calls. Every module should use:

    from su_mcp_bridge.core import get_logger
    log = get_logger(__name__)
    log.info("...")

Defaults to a clean human-readable format on stderr at INFO level. Override
via env var `SU_MCP_BRIDGE_LOG=DEBUG` (or any standard logging level).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

_DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
_TIME_FORMAT = "%H:%M:%S"
_initialized: bool = False


def _initialize_root() -> None:
    """Configure the root su_mcp_bridge logger once."""
    global _initialized
    if _initialized:
        return

    root = logging.getLogger("su_mcp_bridge")
    if root.handlers:
        # Already configured by the host (e.g. pytest). Do not duplicate.
        _initialized = True
        return

    level_name = os.environ.get("SU_MCP_BRIDGE_LOG", os.environ.get("SKETCHUP_AI_LOG", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT, _TIME_FORMAT))
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
    _initialized = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger under the `su_mcp_bridge` namespace.

    `name` is typically `__name__`. If it does not start with `su_mcp_bridge`,
    we still nest it under that namespace so all logs share one root config.
    """
    _initialize_root()
    if not name:
        return logging.getLogger("su_mcp_bridge")
    if name.startswith("su_mcp_bridge"):
        return logging.getLogger(name)
    return logging.getLogger(f"su_mcp_bridge.{name}")
