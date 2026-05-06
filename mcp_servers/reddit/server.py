"""reddit-mcp — a Model Context Protocol server exposing r/nba.

Public Reddit JSON endpoints don't require authentication, so the only
config we honour is the User-Agent header (Reddit asks clients to set one).

Run standalone for testing::

    python mcp_servers/reddit/server.py

It speaks MCP over stdio so it can be plugged into any MCP client.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


REDDIT_BASE = "https://www.reddit.com"

# Reddit blocks generic httpx UAs. We use a Mozilla-style UA by default,
# with their recommended structured format also accepted via env override.
DEFAULT_UA = (
    "Mozilla/5.0 (compatible; nba-moa-agents/0.1; "
    "+https://github.com/sven/nba-moa-agents)"
)


def _user_agent() -> str:
    return os.getenv("REDDIT_USER_AGENT", DEFAULT_UA).strip() or DEFAULT_UA


async def _reddit_get(path: str, params: dict[str, Any] | None = None) -> dict:
    headers = {
        "User-Agent": _user_agent(),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    async with httpx.AsyncClient(timeout=10.0, headers=headers, follow_redirects=True) as client:
        r = await client.get(f"{REDDIT_BASE}{path}", params=params)
        r.raise_for_status()
        return r.json()


def _shape(post: dict) -> dict:
    """Trim Reddit's huge post object to the fields we care about."""
    return {
        "title": post.get("title", ""),
        "score": post.get("score", 0),
        "num_comments": post.get("num_comments", 0),
        "author": post.get("author", ""),
        "permalink": f"https://www.reddit.com{post.get('permalink', '')}",
        "url": post.get("url", ""),
        "flair": post.get("link_flair_text", ""),
        "selftext_excerpt": (post.get("selftext", "") or "")[:280],
    }


mcp = FastMCP("reddit")


# ─── Tools ───────────────────────────────────────────────────────────────────


@mcp.tool(
    description=(
        "Get top posts from a subreddit (`r/nba` by default) for a selected timeframe. "
        "Use for highest-scoring community sentiment snapshots (`hour|day|week|month|year|all`); not for real-time momentum (use `hot_posts`). "
        "Output JSON includes `subreddit`, `timeframe`, and simplified `posts` fields (title, score, comments, links, flair, excerpt)."
    ),
)
async def top_posts(
    subreddit: str = "nba",
    limit: int = 10,
    timeframe: str = "day",
) -> dict:
    """Return the top posts from a subreddit.

    Args:
        subreddit: defaults to ``"nba"``.
        limit: 1-50, defaults to 10.
        timeframe: one of ``hour``, ``day``, ``week``, ``month``, ``year``,
            ``all``. Defaults to ``"day"``.
    """
    limit = max(1, min(int(limit), 50))
    data = await _reddit_get(
        f"/r/{subreddit}/top.json",
        params={"limit": limit, "t": timeframe},
    )
    children = data.get("data", {}).get("children", [])
    return {"subreddit": subreddit, "timeframe": timeframe, "posts": [_shape(c["data"]) for c in children]}


@mcp.tool(
    description=(
        "Get currently hot posts from a subreddit (`r/nba` by default). "
        "Use for what is actively trending now based on engagement velocity; not for all-time/high-score ranking (use `top_posts`). "
        "Output JSON includes `subreddit` and simplified `posts` payload."
    ),
)
async def hot_posts(subreddit: str = "nba", limit: int = 10) -> dict:
    """Return the currently *hot* posts from a subreddit.

    "Hot" emphasises recent engagement velocity over absolute score.
    """
    limit = max(1, min(int(limit), 50))
    data = await _reddit_get(f"/r/{subreddit}/hot.json", params={"limit": limit})
    children = data.get("data", {}).get("children", [])
    return {"subreddit": subreddit, "posts": [_shape(c["data"]) for c in children]}


@mcp.tool(
    description=(
        "Search posts within one subreddit, sorted by relevance. "
        "Use for targeted questions like 'what is r/nba saying about X'; requires `query`, with optional `subreddit` and `limit` (1-25). "
        "Output JSON includes `subreddit`, `query`, and simplified matching `posts`."
    ),
)
async def search_posts(query: str, subreddit: str = "nba", limit: int = 10) -> dict:
    """Search posts in a subreddit (sorted by relevance).

    Useful for "what is r/nba saying about player X?" type questions.
    """
    limit = max(1, min(int(limit), 25))
    data = await _reddit_get(
        f"/r/{subreddit}/search.json",
        params={"q": query, "restrict_sr": "1", "limit": limit, "sort": "relevance"},
    )
    children = data.get("data", {}).get("children", [])
    return {"subreddit": subreddit, "query": query, "posts": [_shape(c["data"]) for c in children]}


# ─── Resource ────────────────────────────────────────────────────────────────


@mcp.resource("reddit://docs")
def docs() -> str:
    return (
        "reddit-mcp — public Reddit JSON wrapper\n"
        "Tools:\n"
        "  - top_posts(subreddit='nba', limit=10, timeframe='day')\n"
        "  - hot_posts(subreddit='nba', limit=10)\n"
        "  - search_posts(query, subreddit='nba', limit=10)\n"
        "Honours REDDIT_USER_AGENT env var.\n"
    )


if __name__ == "__main__":
    mcp.run()
