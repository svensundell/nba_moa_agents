"""StatsAgent — uses the ``nba_stats`` MCP server's ``player_stats_by_name``
combined helper to resolve player names to season averages.

Player names are extracted from the user query with a light regex; for each
candidate we make one MCP call. If the query is empty (daily-brief mode) the
agent emits a neutral proposal — there's no single "default" set of stats
that would be relevant to every brief.
"""

from __future__ import annotations

import re

from app.moa.agents.base import (
    MCPToolError,
    call_llm,
    event,
    make_proposal,
    mcp_invoke,
    parse_mcp_json,
)
from app.moa.state import MoAState

_NAME_RE = re.compile(r"\b([A-Z][a-z]{2,})\s+([A-Z][a-z]{2,})\b")


SYSTEM = """You are a statistical analyst for the NBA.
Given season-average data for some players, write a short paragraph
contextualising their current form.

Rules:
- Cite numbers (PPG, RPG, APG, FG%, 3P%) when present.
- Be conservative: do not invent stats.
- If no data is provided, say "No statistical context available."
"""


async def stats_agent(state: MoAState) -> dict:
    query = state.get("query") or ""
    candidates = list({f"{a} {b}" for a, b in _NAME_RE.findall(query)})[:3]

    if not candidates:
        prop = make_proposal(
            "stats",
            "No specific players referenced in this query.",
            sources=[],
        )
        return {
            "proposals": [prop],
            "events": [event("stats", "proposer", "done", content="no candidates", model=prop.model)],
        }

    rows: list[dict] = []
    tool_events = []
    for name in candidates:
        try:
            raw, tev = await mcp_invoke(
                "stats",
                "nba_stats_player_stats_by_name",
                {"name": name},
            )
        except MCPToolError as exc:
            return {
                "proposals": [make_proposal("stats", f"MCP error: {exc}")],
                "events": [event("stats", "proposer", "error", content=str(exc))],
            }

        tool_events.append(tev)
        payload = parse_mcp_json(raw)
        if not isinstance(payload, dict) or not payload.get("player") or not payload.get("averages"):
            continue
        p = payload["player"]
        a = payload["averages"]
        rows.append(
            {
                "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
                "team": p.get("team", ""),
                "ppg": a.get("pts"),
                "rpg": a.get("reb"),
                "apg": a.get("ast"),
                "fg_pct": a.get("fg_pct"),
                "fg3_pct": a.get("fg3_pct"),
                "games": a.get("games_played"),
            }
        )

    if not rows:
        prop = make_proposal(
            "stats",
            "Players were referenced but no current-season averages were available.",
            sources=["mcp:nba_stats"],
        )
        return {
            "proposals": [prop],
            "events": [*tool_events, event("stats", "proposer", "done", content="no rows", model=prop.model)],
        }

    lines = [
        f"- {r['name']} ({r['team']}): {r['ppg']} PPG, {r['rpg']} RPG, "
        f"{r['apg']} APG, {r['fg_pct']} FG%, {r['fg3_pct']} 3P% over {r['games']} GP"
        for r in rows
    ]
    raw_text = "\n".join(lines)
    summary = await call_llm("stats", system=SYSTEM, user=f"Stats:\n{raw_text}\n\nWrite the paragraph.")

    prop = make_proposal(
        "stats",
        summary,
        sources=["mcp:nba_stats:player_stats_by_name"],
        raw=raw_text,
    )
    return {
        "proposals": [prop],
        "events": [
            *tool_events,
            event("stats", "proposer", "done", content=summary[:160], model=prop.model),
        ],
    }
