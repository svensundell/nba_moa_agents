"""StatsAgent — tool-using proposer for standout players context."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage

from app.mcp.client import mcp_registry
from app.moa.agents.base import (
    event,
    make_proposal,
    record_streamed_llm_call,
    record_streamed_tool_call,
)
from app.moa.llm import AGENT_MODELS, get_model, model_id
from app.moa.state import MoAState

SYSTEM = """You are an NBA stats reporter for a daily morning brief.

Your task:
1) Identify 2-3 standout players from last night's games (positive and/or negative impact).
2) Use tools to ground each player in evidence — favouring exact statlines:
   - `espn_nba_scoreboard(date)` for the list of last-night games and their event ids
   - `espn_nba_boxscore(event_id)` for the per-player statline of any game
   - `espn_nba_headlines` for the discussion signal around a player
   - `nba_stats_get_games` / `nba_stats_search_players` for cross-checks if needed
3) Pick standouts using the boxscore: high PTS, REB, AST, STL, BLK, efficient FG/3PT,
   blowout +/-, OR notably bad lines (e.g. very low FG efficiency, many turnovers).
4) Write concise bullets that include the EXACT statline you found, like:
   `Austin Reaves (Lakers): 8 pts on 3-of-16 FG, 4 turnovers in 108-90 loss to OKC.`

Rules:
- Always pull at least one boxscore via `espn_nba_boxscore` before concluding.
- Keep tool usage lean: at most 6 total tool calls. Don't pull every game's box score —
  pick 1-2 games (closest game, biggest blowout, or most-headlined matchup).
- Only cite numbers that came from a tool response. Never invent stats.
- If data is thin, say that clearly.
- Keep output to max 6 bullets, neutral tone, no emojis.
"""

_ALLOWED_TOOL_NAMES = {
    "espn_nba_headlines",
    "espn_nba_scoreboard",
    "espn_nba_boxscore",
    "nba_stats_get_games",
    "nba_stats_search_players",
}


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: list[str] = []
        for block in content:
            if isinstance(block, str):
                out.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                out.append(str(block.get("text", "")))
        return "\n".join(out).strip()
    return str(content).strip()


def _final_answer_from_any_messages(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            text = _extract_text(msg.content)
            if text:
                return text
        elif isinstance(msg, dict) and msg.get("type") == "ai":
            text = _extract_text(msg.get("content", ""))
            if text:
                return text
    return "No statistical context available."


def _stats_tools() -> list[Any]:
    return [tool for tool in mcp_registry.all_tools if tool.name in _ALLOWED_TOOL_NAMES]


async def stats_agent(state: MoAState) -> dict:
    date_str = state.get("date", "")
    mode = state.get("mode", "brief")
    query = state.get("query", "")
    try:
        anchor_date = datetime.fromisoformat(date_str).date() if date_str else date.today()
    except ValueError:
        anchor_date = date.today()
    previous_date = (anchor_date - timedelta(days=1)).isoformat()
    current_date = anchor_date.isoformat()

    model_name = AGENT_MODELS.get("stats", "reasoner")
    model = get_model(model_name, temperature=0.2)
    model_label = model_id(model_name)
    tools = _stats_tools()
    if not tools:
        prop = make_proposal(
            "stats",
            "No statistical context available because required MCP tools are missing.",
            sources=["mcp:registry"],
        )
        return {
            "proposals": [prop],
            "events": [
                event(
                    "stats",
                    "proposer",
                    "error",
                    content="stats tools unavailable",
                    model=model_label,
                )
            ],
        }

    user_prompt = (
        f"Mode: {mode}\n"
        f"Anchor date: {current_date}\n"
        f"Last-night date: {previous_date}\n"
        f"User query (if any): {query or '(none)'}\n\n"
        "Suggested workflow:\n"
        f"  1) Call `espn_nba_scoreboard(date='{previous_date}')` to list last night's games.\n"
        "  2) Pick 1-2 games (closest score, biggest blowout, or biggest names).\n"
        "  3) Call `espn_nba_boxscore(event_id=...)` for each picked game.\n"
        "  4) Optionally cross-check with `espn_nba_headlines` to see who is being discussed.\n"
        "Return 4-6 bullets with EXACT statlines (PTS / FG / 3PT / REB / AST / TO).\n"
        "Cap at 6 tool calls total. Stop early if you have enough."
    )

    agent = create_agent(model=model, tools=tools, system_prompt=SYSTEM)
    tool_events = []
    final_messages: list[Any] = []
    seen_tool_events: set[tuple[str, str]] = set()
    tool_start_times: dict[str, float] = {}
    llm_start_times: dict[str, float] = {}

    try:
        async for trace_event in agent.astream_events(
            {"messages": [{"role": "user", "content": user_prompt}]},
            version="v2",
        ):
            evt_type = trace_event.get("event")
            run_id = str(trace_event.get("run_id", ""))
            if evt_type == "on_tool_start":
                tool_start_times[run_id] = time.monotonic()
            elif evt_type == "on_tool_end":
                tool_name = str(trace_event.get("name", "tool"))
                output = trace_event.get("data", {}).get("output")
                preview = _extract_text(output)[:220].replace("\n", " ")
                latency_ms = (
                    time.monotonic() - tool_start_times.pop(run_id, time.monotonic())
                ) * 1000.0
                record_streamed_tool_call("stats", trace_event, latency_ms=latency_ms)
                dedupe_key = (tool_name, preview)
                if dedupe_key in seen_tool_events:
                    continue
                seen_tool_events.add(dedupe_key)
                tool_events.append(
                    event(
                        "stats",
                        "proposer",
                        "tool",
                        content=f"{tool_name}: {preview}",
                        model=model_label,
                    )
                )
            elif evt_type == "on_chat_model_start":
                llm_start_times[run_id] = time.monotonic()
            elif evt_type == "on_chat_model_end":
                latency_ms = (
                    time.monotonic() - llm_start_times.pop(run_id, time.monotonic())
                ) * 1000.0
                record_streamed_llm_call(
                    "stats",
                    model_label,
                    trace_event,
                    fallback_latency_ms=latency_ms,
                )
            elif evt_type == "on_chain_end":
                output = trace_event.get("data", {}).get("output")
                if isinstance(output, dict):
                    messages = output.get("messages")
                    if isinstance(messages, list):
                        final_messages = messages
        summary = _final_answer_from_any_messages(final_messages)
    except Exception as exc:
        prop = make_proposal("stats", f"Stats agent failed: {exc}", sources=["mcp:stats"])
        return {
            "proposals": [prop],
            "events": [
                *tool_events,
                event("stats", "proposer", "error", content=str(exc), model=model_label),
            ],
        }

    prop = make_proposal(
        "stats",
        summary,
        sources=[
            "mcp:espn:nba_headlines",
            "mcp:espn:nba_scoreboard",
            "mcp:espn:nba_boxscore",
            "mcp:nba_stats:get_games",
            "mcp:nba_stats:search_players",
        ],
    )
    return {
        "proposals": [prop],
        "events": [
            *tool_events,
            event("stats", "proposer", "done", content=summary[:160], model=prop.model),
        ],
    }
