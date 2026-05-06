"""InjuriesAgent — uses ``espn_nba_injury_headlines`` for server-side filtering.

Now that the ESPN MCP server exposes a dedicated injury-filtered tool, this
agent simply consumes its output and asks the LLM to format the medical
desk briefing.
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

SYSTEM = """You are an NBA medical desk reporter.
Given a list of injury-related headlines, return:
1. A bullet list (max 6) of impacted players and reported status.
2. A one-line "fantasy/betting takeaway" if obvious; otherwise omit.

Stay strictly factual; do not speculate beyond what is in the headlines.
Grounding rules:
- Only include a team in parentheses if the team name appears explicitly in the provided headlines.
- Never infer or "remember" a player's team from prior knowledge.
- If team is not explicitly present in the tool data, omit team and write only the player name.
If no items are provided, output exactly: "No injury news in the current feed."
"""


async def injuries_agent(state: MoAState) -> dict:
    try:
        raw, tool_event = await mcp_invoke(
            "injuries",
            "espn_nba_injury_headlines",
            {"limit": 10},
        )
    except MCPToolError as exc:
        return {
            "proposals": [make_proposal("injuries", f"MCP error: {exc}")],
            "events": [event("injuries", "proposer", "error", content=str(exc))],
        }

    payload = parse_mcp_json(raw)
    items = payload.get("items", []) if isinstance(payload, dict) else []

    if not items:
        prop = make_proposal(
            "injuries",
            "No injury news in the current feed.",
            sources=["mcp:espn"],
        )
        return {
            "proposals": [prop],
            "events": [tool_event, event("injuries", "proposer", "done", content="none", model=prop.model)],
        }

    snippets = "\n".join(f"- {i['title']} — {(i.get('summary') or '')[:160]}" for i in items)
    summary = await call_llm("injuries", system=SYSTEM, user=f"Headlines:\n{snippets}")

    prop = make_proposal(
        "injuries",
        summary,
        sources=[i["link"] for i in items[:5] if i.get("link")],
        raw=snippets,
    )
    return {
        "proposals": [prop],
        "events": [
            tool_event,
            event("injuries", "proposer", "done", content=summary[:160], model=prop.model),
        ],
    }
