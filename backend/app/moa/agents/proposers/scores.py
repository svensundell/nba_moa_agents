"""ScoresAgent — uses the ``nba_stats`` MCP server's ``get_games`` tool.

Strict MCP-only: no HTTP fallback. If the tool isn't available the agent
emits an error event and returns an empty proposal.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

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
Given two game lists:
- last night's games (finals and late games from the previous US evening)
- upcoming games for the current date
write a concise summary (max 10 bullet points).

Rules:
- Use exactly two sections:
  1) "Last Night Results"
  2) "Upcoming Games"
- In "Last Night Results", highlight blowouts (margin >= 20), overtime games,
  and close finishes when obvious from scorelines.
- In "Upcoming Games", list key matchups that have not started yet.
- If one section has no games, say so explicitly for that section.
- Use emoji-free, neutral journalistic tone.
- Cite team names exactly as in the data.
"""


async def scores_agent(state: MoAState) -> dict:
    date_str = state.get("date", "")
    try:
        anchor_date = datetime.fromisoformat(date_str).date() if date_str else date.today()
    except ValueError:
        anchor_date = date.today()
    previous_date = (anchor_date - timedelta(days=1)).isoformat()
    current_date = anchor_date.isoformat()

    try:
        raw_prev, prev_event = await mcp_invoke(
            "scores",
            "nba_stats_get_games",
            {"date": previous_date},
        )
        raw_today, today_event = await mcp_invoke(
            "scores",
            "nba_stats_get_games",
            {"date": current_date},
        )
    except MCPToolError as exc:
        return {
            "proposals": [
                make_proposal("scores", f"MCP error: {exc}", sources=[])
            ],
            "events": [event("scores", "proposer", "error", content=str(exc))],
        }

    payload_prev = parse_mcp_json(raw_prev)
    payload_today = parse_mcp_json(raw_today)
    previous_games = payload_prev.get("data", []) if isinstance(payload_prev, dict) else []
    today_games = payload_today.get("data", []) if isinstance(payload_today, dict) else []

    if not previous_games and not today_games:
        prop = make_proposal(
            "scores",
            f"No NBA games found for {previous_date} or {current_date}.",
            sources=["mcp:nba_stats"],
        )
        return {
            "proposals": [prop],
            "events": [
                prev_event,
                today_event,
                event("scores", "proposer", "done", content="no games", model=prop.model),
            ],
        }

    previous_snippets = []
    for g in previous_games:
        home = g.get("home_team", {}).get("full_name", "?")
        away = g.get("visitor_team", {}).get("full_name", "?")
        hs = g.get("home_team_score")
        vs = g.get("visitor_team_score")
        status = g.get("status", "")
        previous_snippets.append(f"- {away} @ {home} | {vs}-{hs} | status: {status}")

    today_snippets = []
    for g in today_games:
        home = g.get("home_team", {}).get("full_name", "?")
        away = g.get("visitor_team", {}).get("full_name", "?")
        hs = g.get("home_team_score")
        vs = g.get("visitor_team_score")
        status = g.get("status", "")
        today_snippets.append(f"- {away} @ {home} | {vs}-{hs} | status: {status}")

    user_prompt = (
        f"Anchor date: {current_date}\n"
        f"Last-night date: {previous_date}\n\n"
        "Last-night games:\n"
        + ("\n".join(previous_snippets) if previous_snippets else "- none")
        + "\n\nUpcoming/current-date games:\n"
        + ("\n".join(today_snippets) if today_snippets else "- none")
        + "\n\nWrite the summary."
    )
    summary = await call_llm("scores", system=SYSTEM, user=user_prompt)

    prop = make_proposal(
        "scores",
        summary,
        sources=["mcp:nba_stats:get_games"],
        raw=(
            "Last-night games:\n"
            + ("\n".join(previous_snippets) if previous_snippets else "- none")
            + "\n\nUpcoming/current-date games:\n"
            + ("\n".join(today_snippets) if today_snippets else "- none")
        ),
    )
    return {
        "proposals": [prop],
        "events": [
            prev_event,
            today_event,
            event("scores", "proposer", "done", content=summary[:160], model=prop.model),
        ],
    }
