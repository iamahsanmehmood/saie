"""Allow running as: python -m su_mcp_bridge.mcp_server"""

from .server import mcp

mcp.run(transport="stdio")
