"""espn-mcp — a Model Context Protocol server wrapping ESPN's NBA endpoints.

Exposes NBA-flavoured tools that an LLM agent (Claude Desktop, Cursor,
LangGraph, ...) can call directly:

- ``nba_headlines`` — last N headlines from the official ESPN NBA news feed.
- ``nba_injury_headlines`` — headlines filtered to injury / availability news.
- ``nba_scoreboard`` — list of games for a date with event ids and scores.
- ``nba_boxscore`` — per-player statlines for a given ESPN event id.

Run standalone:

    python mcp_servers/espn/server.py
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import feedparser
import httpx
from mcp.server.fastmcp import FastMCP


ESPN_NBA_RSS = "https://www.espn.com/espn/rss/nba/news"
ESPN_SITE_API = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"

INJURY_KEYWORDS = (
    "injur",
    "out for",
    "questionable",
    "doubtful",
    "ruled out",
    "knee",
    "ankle",
    "hamstring",
    "achilles",
    "shoulder",
    "concussion",
    "surgery",
    "miss",
    "sidelined",
    "MRI",
)


async def _fetch_feed() -> list[dict[str, Any]]:
    """Download and parse the ESPN NBA RSS feed."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(ESPN_NBA_RSS)
        r.raise_for_status()
        content = r.text

    parsed = feedparser.parse(content)
    return [
        {
            "title": e.get("title", ""),
            "summary": (e.get("summary", "") or "").strip(),
            "link": e.get("link", ""),
            "published": e.get("published", ""),
            "id": e.get("id", e.get("link", "")),
        }
        for e in parsed.entries
    ]


def _is_injury(item: dict[str, Any]) -> bool:
    blob = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    return any(k.lower() in blob for k in INJURY_KEYWORDS)


mcp = FastMCP("espn")


# ─── Tools ───────────────────────────────────────────────────────────────────


@mcp.tool(
    description=(
        "Return latest NBA headlines from ESPN's official RSS feed. "
        "Use for news roundups and breaking updates; `limit` is clamped to 1-50. "
        "Output JSON includes `source`, `count`, and `items` with title, summary, link, published timestamp, and id."
    ),
)
async def nba_headlines(limit: int = 15) -> dict:
    """Return the most recent NBA headlines from ESPN's RSS feed.

    Args:
        limit: 1-50, defaults to 15.
    """
    limit = max(1, min(int(limit), 50))
    items = await _fetch_feed()
    return {"source": "espn.com/rss/nba", "count": min(limit, len(items)), "items": items[:limit]}


@mcp.tool(
    description=(
        "Return NBA headlines that match injury/availability keywords (questionable, ruled out, MRI, etc.). "
        "Use when the user specifically asks about injuries; not for full unfiltered news (use `nba_headlines`). "
        "Output JSON mirrors headlines format with keyword-filtered `items`; `limit` is clamped to 1-30."
    ),
)
async def nba_injury_headlines(limit: int = 10) -> dict:
    """Return ESPN headlines filtered to injury / availability news only.

    The filter is keyword-based (covers "injur", "questionable", "ruled out",
    body parts, "MRI", etc.).
    """
    limit = max(1, min(int(limit), 30))
    items = await _fetch_feed()
    relevant = [i for i in items if _is_injury(i)]
    return {
        "source": "espn.com/rss/nba",
        "count": min(limit, len(relevant)),
        "items": relevant[:limit],
    }


async def _espn_get(path: str, params: dict[str, Any] | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(f"{ESPN_SITE_API}{path}", params=params)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError:
            return {
                "error": "espn_request_failed",
                "status_code": r.status_code,
                "path": path,
                "params": params or {},
                "message": r.text[:200],
            }
        return r.json()


def _format_score_for_game(game: dict[str, Any]) -> dict[str, Any]:
    competitions = game.get("competitions", [])
    if not competitions:
        return {}
    comp = competitions[0]
    competitors = comp.get("competitors", [])
    teams: list[dict[str, Any]] = []
    for c in competitors:
        team = c.get("team", {}) or {}
        teams.append(
            {
                "abbrev": team.get("abbreviation", ""),
                "display": team.get("displayName", ""),
                "home_away": c.get("homeAway", ""),
                "score": c.get("score", ""),
                "winner": c.get("winner", False),
            }
        )
    status = (game.get("status") or {}).get("type", {}) or {}
    return {
        "event_id": str(game.get("id", "")),
        "name": game.get("name", ""),
        "short_name": game.get("shortName", ""),
        "status": status.get("description", ""),
        "completed": bool(status.get("completed")),
        "start": game.get("date", ""),
        "teams": teams,
    }


@mcp.tool(
    description=(
        "List NBA games for a date (`YYYY-MM-DD`) from ESPN site API scoreboard. "
        "Use to get event ids, scores, and statuses before calling `nba_boxscore`; defaults to yesterday if no date is provided. "
        "Output JSON has `date`, `count`, and `games` entries with `event_id`, teams, start time, and completion status."
    ),
)
async def nba_scoreboard(date: str | None = None) -> dict:
    """List NBA games for a given date (YYYY-MM-DD).

    Defaults to *yesterday* — perfect for a "last night" briefing. Each game
    contains the ESPN ``event_id`` you can pass to ``nba_boxscore`` to get the
    per-player statlines.
    """
    target = date or (dt.date.today() - dt.timedelta(days=1)).isoformat()
    espn_date = target.replace("-", "")
    raw = await _espn_get("/scoreboard", params={"dates": espn_date})
    if "error" in raw:
        return raw
    games = [_format_score_for_game(e) for e in raw.get("events", [])]
    return {"source": "espn.site.api", "date": target, "count": len(games), "games": games}


# Map ESPN's verbose stat keys to the short labels we want in the response.
_ESPN_KEY_TO_SHORT: dict[str, str] = {
    "minutes": "MIN",
    "points": "PTS",
    "fieldGoalsMade-fieldGoalsAttempted": "FG",
    "threePointFieldGoalsMade-threePointFieldGoalsAttempted": "3PT",
    "freeThrowsMade-freeThrowsAttempted": "FT",
    "rebounds": "REB",
    "offensiveRebounds": "OREB",
    "defensiveRebounds": "DREB",
    "assists": "AST",
    "steals": "STL",
    "blocks": "BLK",
    "turnovers": "TO",
    "fouls": "PF",
    "plusMinus": "+/-",
}


def _flatten_boxscore_team(team_block: dict[str, Any]) -> dict[str, Any]:
    team_info = team_block.get("team", {}) or {}
    statistics = team_block.get("statistics", []) or []
    out_players: list[dict[str, Any]] = []
    for group in statistics:
        keys: list[str] = group.get("keys", []) or []
        athletes = group.get("athletes", []) or []
        for entry in athletes:
            athlete = entry.get("athlete", {}) or {}
            stats: list[str] = entry.get("stats", []) or []
            stat_map: dict[str, str] = {}
            for k, v in zip(keys, stats):
                short = _ESPN_KEY_TO_SHORT.get(k)
                if short:
                    stat_map[short] = v
            out_players.append(
                {
                    "name": athlete.get("displayName", ""),
                    "position": (athlete.get("position", {}) or {}).get("abbreviation", ""),
                    "starter": entry.get("starter", False),
                    "did_not_play": entry.get("didNotPlay", False),
                    "stats": stat_map,
                }
            )
    return {
        "abbrev": team_info.get("abbreviation", ""),
        "display": team_info.get("displayName", ""),
        "players": out_players,
    }


@mcp.tool(
    description=(
        "Fetch per-player box score statlines for a single ESPN `event_id`. "
        "Use after `nba_scoreboard` when you need athlete-level stats (MIN, FG, 3PT, FT, REB, AST, STL, BLK, TO, PF, +/- , PTS). "
        "Output JSON includes game header/status plus both teams and flattened player stat maps."
    ),
)
async def nba_boxscore(event_id: str) -> dict:
    """Return the per-player statlines for a given ESPN NBA ``event_id``.

    Use ``nba_scoreboard`` first to get the event id for the game you care
    about. The response includes both teams' rosters with MIN, FG, 3PT, FT,
    REB, AST, STL, BLK, TO, PF, +/- and PTS for every athlete that dressed.
    """
    raw = await _espn_get("/summary", params={"event": str(event_id)})
    if "error" in raw:
        return raw
    boxscore = raw.get("boxscore", {}) or {}
    teams_payload = boxscore.get("players", []) or []
    teams = [_flatten_boxscore_team(t) for t in teams_payload]
    header = raw.get("header", {}) or {}
    competitions = header.get("competitions", [{}])
    comp = competitions[0] if competitions else {}
    return {
        "source": "espn.site.api",
        "event_id": str(event_id),
        "name": header.get("name", ""),
        "status": (comp.get("status", {}) or {}).get("type", {}).get("description", ""),
        "teams": teams,
    }


# ─── Resource ────────────────────────────────────────────────────────────────


@mcp.resource("espn://docs")
def docs() -> str:
    return (
        "espn-mcp — ESPN NBA wrapper\n"
        "Tools:\n"
        "  - nba_headlines(limit=15)\n"
        "  - nba_injury_headlines(limit=10)\n"
        "  - nba_scoreboard(date?)             games for a date with event ids\n"
        "  - nba_boxscore(event_id)            per-player statlines for a game\n"
    )


if __name__ == "__main__":
    mcp.run()
