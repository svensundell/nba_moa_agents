"""NewsAgent — calls the ``espn`` MCP server's ``nba_headlines`` tool."""

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

SYSTEM = """You are an NBA news editor scanning headlines.
Given a list of recent ESPN headlines (title + summary + link), produce a
short briefing of the 5 most important stories.

Rules:
- Group items by theme (trades, contracts, on-court, off-court).
- One sentence per story, neutral tone.
- Mention named players and teams explicitly.
- Skip pure opinion pieces and listicles.
"""


async def news_agent(state: MoAState) -> dict:
    query = state.get("query") or ""

    try:
        raw, tool_event = await mcp_invoke(
            "news",
            "espn_nba_headlines",
            {"limit": 15},
        )
    except MCPToolError as exc:
        return {
            "proposals": [make_proposal("news", f"MCP error: {exc}")],
            "events": [event("news", "proposer", "error", content=str(exc))],
        }

    payload = parse_mcp_json(raw)
    items = payload.get("items", []) if isinstance(payload, dict) else []

    if not items:
        prop = make_proposal(
            "news",
            "ESPN feed returned no headlines.",
            sources=["mcp:espn"],
        )
        return {
            "proposals": [prop],
            "events": [
                tool_event,
                event("news", "proposer", "done", content="no items", model=prop.model),
            ],
        }

    snippets = "\n".join(f"- {i['title']} — {(i.get('summary') or '')[:140]}" for i in items)
    user = (
        f"User question: {query}\n\n" if query else ""
    ) + f"Headlines:\n{snippets}\n\nWrite the briefing."
    summary = await call_llm("news", system=SYSTEM, user=user)

    sources = [i["link"] for i in items[:5] if i.get("link")]
    prop = make_proposal("news", summary, sources=sources, raw=snippets)
    return {
        "proposals": [prop],
        "events": [
            tool_event,
            event("news", "proposer", "done", content=summary[:160], model=prop.model),
        ],
    }
