"""espn-mcp — a Model Context Protocol server wrapping ESPN's NBA RSS feed.

Exposes two NBA-flavoured tools that an LLM agent (Claude Desktop, Cursor,
LangGraph, ...) can call directly:

- ``nba_headlines`` — last N headlines from the official ESPN NBA news feed.
- ``nba_injury_headlines`` — headlines filtered to injury / availability news.

Run standalone:

    python mcp_servers/espn/server.py
"""

from __future__ import annotations

from typing import Any

import feedparser
import httpx
from mcp.server.fastmcp import FastMCP


ESPN_NBA_RSS = "https://www.espn.com/espn/rss/nba/news"

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


@mcp.tool()
async def nba_headlines(limit: int = 15) -> dict:
    """Return the most recent NBA headlines from ESPN's RSS feed.

    Args:
        limit: 1-50, defaults to 15.
    """
    limit = max(1, min(int(limit), 50))
    items = await _fetch_feed()
    return {"source": "espn.com/rss/nba", "count": min(limit, len(items)), "items": items[:limit]}


@mcp.tool()
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


# ─── Resource ────────────────────────────────────────────────────────────────


@mcp.resource("espn://docs")
def docs() -> str:
    return (
        "espn-mcp — ESPN NBA RSS wrapper\n"
        "Tools:\n"
        "  - nba_headlines(limit=15)\n"
        "  - nba_injury_headlines(limit=10)\n"
    )


if __name__ == "__main__":
    mcp.run()
