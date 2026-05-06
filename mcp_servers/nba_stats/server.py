"""nba-stats-mcp — a Model Context Protocol server exposing balldontlie.io.

This is the project's flagship MCP integration. Any LLM client that speaks
MCP (Claude Desktop, Cursor, our own LangGraph agents, etc.) can plug into
this server and immediately gain access to NBA games, players and teams.

Run it standalone for testing::

    python mcp_servers/nba_stats/server.py

It also runs as a stdio child process when launched by the FastAPI backend
through ``MultiServerMCPClient``.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


BDL_BASE = "https://api.balldontlie.io/v1"
MAX_429_RETRIES = 3


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    key = os.getenv("BALLDONTLIE_API_KEY", "").strip()
    if key:
        headers["Authorization"] = key
    return headers


async def _bdl_get(path: str, params: dict[str, Any] | None = None) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        last_response: httpx.Response | None = None
        for attempt in range(MAX_429_RETRIES + 1):
            r = await client.get(f"{BDL_BASE}{path}", params=params, headers=_headers())
            last_response = r
            if r.status_code != 429:
                break
            if attempt >= MAX_429_RETRIES:
                break
            retry_after = r.headers.get("Retry-After", "").strip()
            wait_s = 0.6 * (2**attempt)
            try:
                if retry_after:
                    wait_s = max(wait_s, float(retry_after))
            except ValueError:
                pass
            await asyncio.sleep(wait_s)
        if last_response is None:
            return {
                "error": "balldontlie_request_failed",
                "status_code": 500,
                "path": path,
                "params": params or {},
                "message": "No response from balldontlie",
            }
        r = last_response
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError:
            # Return a structured error payload so MCP tool calls do not crash the
            # whole NBA Copilot flow on provider auth/tier limitations.
            return {
                "error": "balldontlie_request_failed",
                "status_code": r.status_code,
                "path": path,
                "params": params or {},
                "message": r.text.strip() or "Request failed",
            }
        return r.json()


mcp = FastMCP("nba-stats")


# ─── Tools ───────────────────────────────────────────────────────────────────


@mcp.tool(
    description=(
        "Fetch NBA games for a specific ISO date (`YYYY-MM-DD`) from balldontlie. "
        "Use when the user asks for final scores, schedule, or game status on one day; if `date` is omitted, defaults to yesterday for last-night recaps. "
        "Output is balldontlie `/games` JSON with game records including teams, scores, and status."
    ),
)
async def get_games(date: str | None = None) -> dict:
    """Get NBA games for a given ISO date (YYYY-MM-DD).

    If ``date`` is omitted, returns games for *yesterday* (most useful for a
    "last night" briefing). Each game includes the home/visitor team objects,
    final or in-progress scores, and game status.
    """
    target = date or (dt.date.today() - dt.timedelta(days=1)).isoformat()
    return await _bdl_get("/games", params={"dates[]": target, "per_page": 25})


@mcp.tool(
    description=(
        "Fuzzy-search NBA players by name via balldontlie `/players`. "
        "Use when you need to resolve a player's canonical id/team before other calls; not for box scores or game outcomes. "
        "Parameters: `name` (required search text), `per_page` (max matches to return). Output is balldontlie player-search JSON."
    ),
)
async def search_players(name: str, per_page: int = 5) -> dict:
    """Fuzzy-search NBA players by name (e.g. 'doncic', 'lebron').

    Returns up to ``per_page`` matches with team membership.
    """
    return await _bdl_get("/players", params={"search": name, "per_page": per_page})


@mcp.tool(
    description=(
        "List NBA teams (conference/division metadata) from balldontlie `/teams`. "
        "Use when you need team ids or basic team context; not for recent results or player lookups. "
        "Output is balldontlie teams JSON."
    ),
)
async def list_teams() -> dict:
    """List all 30 NBA teams with their conference and division."""
    return await _bdl_get("/teams")


@mcp.tool(
    description=(
        "Get a single team's recent games over the last N days using balldontlie `/games`. "
        "Use for short-term form/streak checks before analysis; requires numeric `team_id` and optional `days` window (default 7). "
        "Output is balldontlie games JSON filtered by `team_ids[]` and date range."
    ),
)
async def team_recent_games(team_id: int, days: int = 7) -> dict:
    """Get a team's games in the last ``days`` days.

    Useful for spotting form streaks before answering a question like
    "How are the Celtics looking this week?"
    """
    end = dt.date.today()
    start = end - dt.timedelta(days=max(days, 1))
    dates = [(start + dt.timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    return await _bdl_get(
        "/games",
        params={"team_ids[]": team_id, "dates[]": dates, "per_page": 50},
    )


# ─── Resources ───────────────────────────────────────────────────────────────


@mcp.resource("nba://docs")
def docs() -> str:
    """Inline documentation that an MCP client can read to understand the server."""
    return (
        "nba-stats-mcp — wraps balldontlie.io v1\n"
        "Tools:\n"
        "  - get_games(date?)                       last-night results by default\n"
        "  - search_players(name, per_page=5)       fuzzy search\n"
        "  - list_teams()                           all 30 teams\n"
        "  - team_recent_games(id, days=7)          form/streak inspector\n"
    )


if __name__ == "__main__":
    # FastMCP defaults to stdio, which is what MultiServerMCPClient uses.
    mcp.run()
