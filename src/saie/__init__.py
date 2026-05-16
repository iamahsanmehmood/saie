"""
SAIE — SketchUp Automation & Intelligence Engine.

This is the canonical user-facing package. The actual implementation lives
in the `su_mcp_bridge` namespace (kept stable for backward compatibility);
this module re-exports the public surface so users can write:

    from saie import get_config, SketchUpWSClient

instead of the legacy:

    from su_mcp_bridge.core.config import get_config
    from su_mcp_bridge.transport.ws_client import SketchUpWSClient

Both forms continue to work. New code should prefer `saie`.
"""

from su_mcp_bridge import __version__ as __version__  # noqa: F401
from su_mcp_bridge.core.config import (
    SaieConfig as SaieConfig,
)
from su_mcp_bridge.core.config import (
    get_config as get_config,
)
from su_mcp_bridge.core.config import (
    load_config as load_config,
)
from su_mcp_bridge.transport.ws_client import SketchUpWSClient as SketchUpWSClient

__all__ = [
    "__version__",
    "SaieConfig",
    "get_config",
    "load_config",
    "SketchUpWSClient",
]
