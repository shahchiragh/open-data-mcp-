"""MCP client wiring for FloodGuard.

In local development the agent can talk to the OpenDataMCP server (the FastMCP
server created in this repo, `open_data_mcp.py`) over an stdio connection. This
gives the agent the full RODA discovery + STAC query + NDVI/NDBI toolset from
that server.

When deployed to Amazon Bedrock AgentCore runtime the local stdio server is not
present, so this returns None and the agent relies on its self-contained
`flood_tools` (which call the same open Earth Search STAC + RODA registry
directly). Set OPEN_DATA_MCP_PATH to enable the stdio client anywhere.
"""

import os
import shutil
import logging

logger = logging.getLogger("floodguard.mcp")


def get_open_data_mcp_client():
    """Return a Strands MCPClient bound to the OpenDataMCP stdio server, or None.

    Enabled only when OPEN_DATA_MCP_PATH points at the open_data_mcp.py script
    and a `uv` (or python) launcher is available. Kept optional so cloud
    deployment never depends on a local process.
    """
    script_path = os.environ.get("OPEN_DATA_MCP_PATH")
    if not script_path or not os.path.exists(script_path):
        logger.info("OpenDataMCP stdio client disabled (OPEN_DATA_MCP_PATH not set).")
        return None

    try:
        from mcp import StdioServerParameters, stdio_client
        from strands.tools.mcp.mcp_client import MCPClient
    except Exception as exc:  # pragma: no cover - import guard
        logger.warning("MCP SDK unavailable, skipping OpenDataMCP client: %s", exc)
        return None

    workdir = os.path.dirname(os.path.abspath(script_path))
    uv = shutil.which("uv")
    if uv:
        command, args = uv, ["run", "--directory", workdir, os.path.basename(script_path)]
    else:
        command, args = shutil.which("python") or "python", [script_path]

    logger.info("Enabling OpenDataMCP stdio client: %s %s", command, args)
    return MCPClient(
        lambda: stdio_client(StdioServerParameters(command=command, args=args))
    )
