"""SocialAgent — calls the ``reddit`` MCP server's ``top_posts`` tool.

If the user asked a specific question, we instead use ``search_posts`` with
the query so the social signal is on-topic rather than just "today's biggest
post on r/nba".
"""

from __future__ import annotations

from app.moa.agents.base import (
    MCPToolError,
    call_llm,
    event,
    make_proposal,
    mcp_invoke,
    parse_mcp_json,
)
from app.moa.state import MoAState

SYSTEM = """You are a community sentiment analyst monitoring r/nba.
Given a list of top posts (title + score + comments + flair), produce:

1. Three bullets summarising the dominant conversation threads of the day.
2. Overall sentiment in one word (positive / negative / mixed / hyped / frustrated).

Skip pure highlight-reel posts. Quote post titles inside double quotes when helpful.
"""


async def social_agent(state: MoAState) -> dict:
    query = (state.get("query") or "").strip()
    use_search = bool(query) and len(query.split()) >= 2

    tool_name = "reddit_search_posts" if use_search else "reddit_top_posts"
    args = (
        {"query": query, "subreddit": "nba", "limit": 10}
        if use_search
        else {"subreddit": "nba", "limit": 15, "timeframe": "day"}
    )

    try:
        raw, tool_event = await mcp_invoke("social", tool_name, args)
    except MCPToolError as exc:
        return {
            "proposals": [make_proposal("social", f"MCP error: {exc}")],
            "events": [event("social", "proposer", "error", content=str(exc))],
        }

    payload = parse_mcp_json(raw)
    posts = payload.get("posts", []) if isinstance(payload, dict) else []

    if not posts:
        prop = make_proposal(
            "social",
            "No relevant r/nba posts found for the requested signal.",
            sources=["mcp:reddit"],
        )
        return {
            "proposals": [prop],
            "events": [tool_event, event("social", "proposer", "done", content="empty", model=prop.model)],
        }

    snippets = "\n".join(
        f"- [{p.get('score', 0)} ↑, {p.get('num_comments', 0)} comments]"
        + (f" {{{p.get('flair')}}}" if p.get("flair") else "")
        + f" {p.get('title', '')}"
        for p in posts
    )
    summary = await call_llm("social", system=SYSTEM, user=f"Posts:\n{snippets}")

    prop = make_proposal(
        "social",
        summary,
        sources=[f"mcp:reddit:{tool_name}"],
        raw=snippets,
    )
    return {
        "proposals": [prop],
        "events": [
            tool_event,
            event("social", "proposer", "done", content=summary[:160], model=prop.model),
        ],
    }
