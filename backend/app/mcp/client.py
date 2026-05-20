"""MCP registry — single source of truth for the LangChain tools exposed by
our three Model Context Protocol servers.

Architecture choice: this project is **strictly MCP-driven**. Agents never
call HTTP endpoints directly; every external interaction goes through an MCP
tool. If the registry isn't initialised (or a tool isn't found) the offending
agent fails loudly so the dependency on MCP stays explicit.

Lifecycle:

1. ``initialize()`` is called once at FastAPI startup (see ``main.py``
   lifespan). It launches each MCP server as a stdio subprocess via
   ``MultiServerMCPClient``, lists the exposed tools, and caches them in a
   process-wide dict keyed by ``"<server>_<tool>"``.
2. Agents look up tools via ``get_tool("nba_stats_get_games")`` and call them
   with ``await tool.ainvoke({...})``.
3. ``shutdown()`` is a no-op today (the adapter manages subprocess lifetimes
   under the hood) but is kept as a hook for future cleanup logic.

The three MCP servers are all custom and live in ``mcp_servers/``:

- ``nba_stats``  — wraps balldontlie.io
- ``reddit``     — wraps Reddit's public JSON
- ``espn``       — wraps ESPN's NBA RSS feed
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from loguru import logger

from app.core.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SERVERS_DIR = PROJECT_ROOT / "mcp_servers"

# Logical server name -> path to its FastMCP entrypoint.
SERVER_PATHS: dict[str, Path] = {
    "nba_stats": SERVERS_DIR / "nba_stats" / "server.py",
    "reddit": SERVERS_DIR / "reddit" / "server.py",
    "espn": SERVERS_DIR / "espn" / "server.py",
}


class MCPNotInitialised(RuntimeError):  # noqa: N818 — explicit non-Error suffix is clearer here
    """Raised when an agent asks for a tool before ``initialize()`` ran."""


class MCPToolMissing(KeyError):  # noqa: N818 — explicit non-Error suffix is clearer here
    """Raised when a requested tool is not in the registry."""


def _server_config() -> dict[str, dict[str, Any]]:
    settings = get_settings()
    cfg: dict[str, dict[str, Any]] = {}
    for name, path in SERVER_PATHS.items():
        if not path.exists():
            logger.warning(f"MCP server entrypoint missing for '{name}': {path}")
            continue
        cfg[name] = {
            "command": sys.executable,
            "args": [str(path)],
            "transport": "stdio",
            "env": {
                **os.environ,
                "BALLDONTLIE_API_KEY": settings.balldontlie_api_key,
                "REDDIT_USER_AGENT": settings.reddit_user_agent,
            },
        }
    return cfg


class MCPRegistry:
    """Process-wide registry of LangChain tools backed by MCP servers."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._client: MultiServerMCPClient | None = None
        self._initialised: bool = False

    @property
    def initialised(self) -> bool:
        return self._initialised

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    @property
    def all_tools(self) -> list[BaseTool]:
        """Return every loaded tool (empty list if not initialised)."""
        return list(self._tools.values())

    @property
    def server_names(self) -> list[str]:
        return list(SERVER_PATHS.keys())

    async def initialize(self) -> None:
        """Connect to every configured MCP server and cache its tools.

        Safe to call multiple times — subsequent calls are no-ops.
        """
        if self._initialised:
            return
        cfg = _server_config()
        if not cfg:
            raise MCPNotInitialised(
                "No MCP server entrypoint found under mcp_servers/. "
                "Cannot run the pipeline without MCP."
            )

        logger.info(f"Initialising MCP registry with servers: {list(cfg)}")
        client = MultiServerMCPClient(cfg, tool_name_prefix=True)
        tools = await client.get_tools()
        for tool in tools:
            self._tools[tool.name] = tool
        self._client = client
        self._initialised = True
        logger.info(f"MCP ready — {len(self._tools)} tools loaded: {self.tool_names}")

    def get_tool(self, name: str) -> BaseTool:
        """Return the tool with the given prefixed name (raises if missing)."""
        if not self._initialised:
            raise MCPNotInitialised(
                "MCP registry was not initialised. Call mcp_registry.initialize() "
                "from the FastAPI lifespan before invoking any agent."
            )
        try:
            return self._tools[name]
        except KeyError as exc:
            raise MCPToolMissing(
                f"MCP tool '{name}' is not in the registry. Available: {self.tool_names}"
            ) from exc

    def get_tools_for(self, server: str) -> list[BaseTool]:
        """Return every tool whose name starts with ``<server>_``."""
        prefix = f"{server}_"
        return [t for t in self._tools.values() if t.name.startswith(prefix)]

    async def shutdown(self) -> None:
        """Tear down the registry. Idempotent."""
        self._tools.clear()
        self._client = None
        self._initialised = False


# Singleton — the rest of the codebase imports this directly.
mcp_registry = MCPRegistry()


# ─── Convenience for agents ──────────────────────────────────────────────────


def _extract_text(content: Any) -> str:
    """Extract the concatenated text payload from an MCP tool ``content`` value.

    The ``langchain-mcp-adapters`` adapter returns the MCP ``CallToolResult``
    content as a list of LangChain content blocks::

        [{"type": "text", "text": "<json>"}, ...]

    When invoked through ``StructuredTool.ainvoke`` LangChain may stringify
    that list into a Python ``repr``. We handle both shapes here.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


async def call_tool(name: str, **kwargs: Any) -> str:
    """Look up an MCP tool and invoke it with the given keyword arguments.

    Returns the tool's *text* payload — typically the JSON string serialised
    by the FastMCP server. Agents pass that through ``parse_mcp_json`` to
    work with native Python objects.

    Raises ``MCPNotInitialised`` / ``MCPToolMissing`` when the registry isn't
    ready or the tool name is unknown — agents convert those into structured
    error events so the failure is visible in the UI trace.
    """
    tool = mcp_registry.get_tool(name)
    # Calling the underlying coroutine directly gives us the raw
    # (content, artifact) tuple instead of LangChain's stringified content,
    # which is much friendlier for downstream JSON parsing.
    coroutine = getattr(tool, "coroutine", None)
    if coroutine is not None:
        content, _artifact = await coroutine(**kwargs)
        return _extract_text(content)
    return _extract_text(await tool.ainvoke(kwargs))
