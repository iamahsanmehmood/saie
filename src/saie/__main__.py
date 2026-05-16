"""Allow `python -m saie` to start the MCP server (stdio transport)."""
from su_mcp_bridge.mcp_server.server import mcp


def main() -> None:
    """Entry point for `python -m saie` and the `saie-mcp` console script."""
    mcp.run()


if __name__ == "__main__":
    main()
