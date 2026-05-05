"""nba-stats-mcp — a Model Context Protocol server exposing balldontlie.io.

This is the project's flagship MCP integration. Any LLM client that speaks
MCP (Claude Desktop, Cursor, our own LangGraph agents, etc.) can plug into
this server and immediately gain access to NBA games, players, teams and
season averages.

Run it standalone for testing::

    python mcp_servers/nba_stats/server.py

It also runs as a stdio child process when launched by the FastAPI backend
through ``MultiServerMCPClient``.
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


BDL_BASE = "https://api.balldontlie.io/v1"


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    key = os.getenv("BALLDONTLIE_API_KEY", "").strip()
    if key:
        headers["Authorization"] = key
    return headers


async def _bdl_get(path: str, params: dict[str, Any] | None = None) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{BDL_BASE}{path}", params=params, headers=_headers())
        r.raise_for_status()
        return r.json()


mcp = FastMCP("nba-stats")


# ─── Tools ───────────────────────────────────────────────────────────────────


@mcp.tool()
async def get_games(date: str | None = None) -> dict:
    """Get NBA games for a given ISO date (YYYY-MM-DD).

    If ``date`` is omitted, returns games for *yesterday* (most useful for a
    "last night" briefing). Each game includes the home/visitor team objects,
    final or in-progress scores, and game status.
    """
    target = date or (dt.date.today() - dt.timedelta(days=1)).isoformat()
    return await _bdl_get("/games", params={"dates[]": target, "per_page": 25})


@mcp.tool()
async def search_players(name: str, per_page: int = 5) -> dict:
    """Fuzzy-search NBA players by name (e.g. 'doncic', 'lebron').

    Returns up to ``per_page`` matches with team membership.
    """
    return await _bdl_get("/players", params={"search": name, "per_page": per_page})


@mcp.tool()
async def player_season_averages(player_id: int, season: int | None = None) -> dict:
    """Get a player's season averages (PPG, RPG, APG, FG%, 3P%, etc.).

    ``season`` defaults to the *previous* calendar year, which matches the
    typical NBA regular-season anchor.
    """
    season = season or dt.date.today().year - 1
    return await _bdl_get(
        "/season_averages", params={"season": season, "player_ids[]": player_id}
    )


@mcp.tool()
async def list_teams() -> dict:
    """List all 30 NBA teams with their conference and division."""
    return await _bdl_get("/teams")


@mcp.tool()
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


@mcp.tool()
async def player_stats_by_name(name: str, season: int | None = None) -> dict:
    """One-shot helper: search by name then fetch season averages.

    Resolves a fuzzy player name (e.g. ``"luka"``) to its top match and
    returns ``{ "player": {...}, "averages": {...} }``. Saves clients from
    chaining ``search_players`` then ``player_season_averages`` themselves.

    Returns ``{"player": null}`` if no player matches.
    """
    players = await _bdl_get("/players", params={"search": name, "per_page": 1})
    rows = players.get("data", [])
    if not rows:
        return {"player": None, "averages": None, "season": season}
    player = rows[0]
    season = season or dt.date.today().year - 1
    averages = await _bdl_get(
        "/season_averages", params={"season": season, "player_ids[]": player["id"]}
    )
    avg_rows = averages.get("data", [])
    return {
        "player": {
            "id": player["id"],
            "first_name": player.get("first_name", ""),
            "last_name": player.get("last_name", ""),
            "team": player.get("team", {}).get("full_name", ""),
            "position": player.get("position", ""),
        },
        "averages": avg_rows[0] if avg_rows else None,
        "season": season,
    }


# ─── Resources ───────────────────────────────────────────────────────────────


@mcp.resource("nba://docs")
def docs() -> str:
    """Inline documentation that an MCP client can read to understand the server."""
    return (
        "nba-stats-mcp — wraps balldontlie.io v1\n"
        "Tools:\n"
        "  - get_games(date?)                       last-night results by default\n"
        "  - search_players(name, per_page=5)       fuzzy search\n"
        "  - player_season_averages(id, season?)    current season by default\n"
        "  - player_stats_by_name(name, season?)    one-shot search + averages\n"
        "  - list_teams()                           all 30 teams\n"
        "  - team_recent_games(id, days=7)          form/streak inspector\n"
    )


if __name__ == "__main__":
    # FastMCP defaults to stdio, which is what MultiServerMCPClient uses.
    mcp.run()
