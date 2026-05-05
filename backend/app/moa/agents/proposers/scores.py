"""ScoresAgent — uses the ``nba_stats`` MCP server's ``get_games`` tool.

Strict MCP-only: no HTTP fallback. If the tool isn't available the agent
emits an error event and returns an empty proposal.
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

SYSTEM = """You are an NBA box-score reporter.
Given a JSON list of games (each with home_team, visitor_team, scores, status),
write a concise summary (max 8 bullet points) of the night's results.

Rules:
- Highlight blowouts (margin >= 20) and overtime games.
- Note any game that has not started yet ("upcoming") separately.
- If no games, say so explicitly.
- Use emoji-free, neutral journalistic tone.
- Cite team names exactly as in the data.
"""


async def scores_agent(state: MoAState) -> dict:
    date = state.get("date", "")

    try:
        raw, tool_event = await mcp_invoke(
            "scores",
            "nba_stats_get_games",
            {"date": date},
        )
    except MCPToolError as exc:
        return {
            "proposals": [
                make_proposal("scores", f"MCP error: {exc}", sources=[])
            ],
            "events": [event("scores", "proposer", "error", content=str(exc))],
        }

    payload = parse_mcp_json(raw)
    games = payload.get("data", []) if isinstance(payload, dict) else []

    if not games:
        prop = make_proposal(
            "scores",
            f"No NBA games found for {date}.",
            sources=["mcp:nba_stats"],
        )
        return {
            "proposals": [prop],
            "events": [tool_event, event("scores", "proposer", "done", content="no games", model=prop.model)],
        }

    snippets = []
    for g in games:
        home = g.get("home_team", {}).get("full_name", "?")
        away = g.get("visitor_team", {}).get("full_name", "?")
        hs = g.get("home_team_score")
        vs = g.get("visitor_team_score")
        status = g.get("status", "")
        snippets.append(f"- {away} @ {home} | {vs}-{hs} | status: {status}")

    user_prompt = f"Date: {date}\nGames:\n" + "\n".join(snippets) + "\n\nWrite the summary."
    summary = await call_llm("scores", system=SYSTEM, user=user_prompt)

    prop = make_proposal(
        "scores",
        summary,
        sources=["mcp:nba_stats:get_games"],
        raw="\n".join(snippets),
    )
    return {
        "proposals": [prop],
        "events": [
            tool_event,
            event("scores", "proposer", "done", content=summary[:160], model=prop.model),
        ],
    }
