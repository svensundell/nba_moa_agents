"""NBA Copilot — tool-using agent for query (chat) mode.

Unlike the deterministic daily-brief MoA graph, this module builds a
tool-using LangChain agent and gives it the full MCP toolset. The agent can
decide which tools to call (and in what order) based on the conversation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from app.api.schemas import RunResult
from app.mcp.client import mcp_registry
from app.moa.llm import AGENT_MODELS, get_model, model_id
from app.moa.state import AgentEvent

NBA_COPILOT_SYSTEM_BASE = """You are an NBA research assistant with access to MCP tools.

Your goal is to answer the user's question with concrete, up-to-date evidence.

Rules:
- Use tools whenever factual data is needed (scores, stats, injuries, fan pulse).
- Prefer free-plan-safe NBA stats tools (players, teams, games) for numeric claims.
- Do not rely on season-averages endpoints; they may be unavailable for this API plan.
- Use ESPN headlines for news and injuries.
- Use Reddit tools for sentiment/community signals.
- If evidence is missing, say so clearly instead of guessing.
- If season averages are unavailable, explicitly say they are unavailable due provider/API plan limits.
- End with a concise markdown answer with optional bullet points.
"""


def _language_instruction(language: str) -> str:
    if language == "fr":
        return (
            "Final answer language: French.\n"
            "Write your final answer in French."
        )
    return "Final answer language: English.\nWrite your final answer in English."


def _event(
    type_: str,
    content: str,
    *,
    model: str = "",
) -> AgentEvent:
    return AgentEvent(
        agent="nba_copilot",
        layer="aggregator",
        type=type_,  # type: ignore[arg-type]
        content=content,
        model=model,
    )


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


def _final_answer(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            text = _extract_text(msg.content)
            if text:
                return text
    return "I could not produce a final answer."


def _final_answer_from_any_messages(messages: list[Any]) -> str:
    """Extract final assistant text from mixed message payloads."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            text = _extract_text(msg.content)
            if text:
                return text
        elif isinstance(msg, dict) and msg.get("type") == "ai":
            text = _extract_text(msg.get("content", ""))
            if text:
                return text
    return "I could not produce a final answer."


def _tool_uses_bdl_season_averages_401(messages: list[BaseMessage]) -> bool:
    """Return True if any tool payload reports balldontlie 401 on season averages."""
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        content = _extract_text(msg.content)
        if (
            '"error": "balldontlie_request_failed"' in content
            and '"status_code": 401' in content
            and '"/season_averages"' in content
        ):
            return True
    return False


def _tool_uses_bdl_season_averages_401_any(messages: list[Any]) -> bool:
    """Return True if any tool payload reports balldontlie 401 on season averages."""
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = _extract_text(msg.content)
        elif isinstance(msg, dict) and msg.get("type") == "tool":
            content = _extract_text(msg.get("content", ""))
        else:
            continue
        if (
            '"error": "balldontlie_request_failed"' in content
            and '"status_code": 401' in content
            and '"/season_averages"' in content
        ):
            return True
    return False


def _filter_nba_copilot_tools() -> list[Any]:
    """Return tool list tailored for free balldontlie plans.

    We intentionally exclude the direct season-averages tool because that
    endpoint is often unavailable on free plans and causes noisy failures.
    """
    blocked = {
        "nba_stats_player_season_averages",
        "nba_stats_player_stats_by_name",
    }
    return [tool for tool in mcp_registry.all_tools if tool.name not in blocked]


def _build_input_messages(
    *,
    query: str,
    messages: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """Build and validate the message list sent to the LangChain agent."""
    out: list[dict[str, str]] = []
    for msg in messages or []:
        role = str(msg.get("role", "")).strip()
        content = str(msg.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        out.append({"role": role, "content": content})
    if not out and query.strip():
        out.append({"role": "user", "content": query.strip()})
    if not out:
        raise ValueError("NBA Copilot requires at least one user message.")
    if not any(msg["role"] == "user" for msg in out):
        raise ValueError("NBA Copilot history must include at least one user message.")
    return out


def _tool_events(messages: list[BaseMessage]) -> list[AgentEvent]:
    events: list[AgentEvent] = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "tool")
            content = _extract_text(msg.content)
            preview = content[:220].replace("\n", " ")
            events.append(_event("tool", f"{tool_name}: {preview}"))
    return events


def _build_nba_copilot_agent(language: str) -> tuple[Any, str, str, list[Any]]:
    """Create model+agent and return (agent, model_name, model_label, tools)."""
    model_name = AGENT_MODELS.get("nba_copilot", "open_query")
    model = get_model(model_name, temperature=0.1)
    model_label = model_id(model_name)
    tools = _filter_nba_copilot_tools()
    if not tools:
        raise RuntimeError("No MCP tools loaded. Ensure MCP registry is initialised.")
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=f"{NBA_COPILOT_SYSTEM_BASE}\n\n{_language_instruction(language)}",
    )
    return agent, model_name, model_label, tools


async def stream_open_query_frames(
    query: str,
    messages: list[dict[str, str]] | None = None,
    date: str | None = None,
    language: str = "en",
) -> AsyncIterator[dict[str, Any]]:
    """Stream NBA Copilot frames live for websocket clients."""
    started_at = datetime.now()
    date_value = date or datetime.now().date().isoformat()
    agent, _model_name, model_label, tools = _build_nba_copilot_agent(language)
    input_messages = _build_input_messages(query=query, messages=messages)

    events: list[AgentEvent] = [
        _event(
            "start",
            f"NBA Copilot started with {len(tools)} MCP tools.",
            model=model_label,
        )
    ]
    yield {"kind": "started", "at": started_at.isoformat(), "mode": "query"}
    yield {"kind": "event", "event": events[0].model_dump(mode="json")}

    final_messages: list[Any] = []
    seen_tool_events: set[tuple[str, str]] = set()

    try:
        async for trace_event in agent.astream_events(
            {"messages": input_messages},
            version="v2",
        ):
            evt_type = trace_event.get("event")
            if evt_type == "on_tool_end":
                tool_name = str(trace_event.get("name", "tool"))
                output = trace_event.get("data", {}).get("output")
                preview = _extract_text(output)[:220].replace("\n", " ")
                dedupe_key = (tool_name, preview)
                if dedupe_key in seen_tool_events:
                    continue
                seen_tool_events.add(dedupe_key)
                ev = _event("tool", f"{tool_name}: {preview}", model=model_label)
                events.append(ev)
                yield {"kind": "event", "event": ev.model_dump(mode="json")}
            elif evt_type == "on_chain_end":
                output = trace_event.get("data", {}).get("output")
                if isinstance(output, dict):
                    messages = output.get("messages")
                    if isinstance(messages, list):
                        final_messages = messages

        answer = _final_answer_from_any_messages(final_messages)
        if _tool_uses_bdl_season_averages_401_any(final_messages):
            answer += (
                "\n\n> Note: balldontlie season averages are unavailable on the current API plan "
                "(401 Unauthorized), so this answer uses other available data sources."
            )

        done = _event("done", "NBA Copilot answer ready.", model=model_label)
        events.append(done)
        yield {"kind": "event", "event": done.model_dump(mode="json")}
    except Exception as exc:
        answer = (
            "I couldn't complete the NBA Copilot run because the LLM call failed.\n\n"
            f"Error: `{exc}`\n\n"
            "Please verify network access / API connectivity and try again."
        )
        err = _event("error", f"NBA Copilot failed: {exc}", model=model_label)
        events.append(err)
        yield {"kind": "event", "event": err.model_dump(mode="json")}

    finished_at = datetime.now()
    result = RunResult(
        mode="query",
        date=date_value,
        query=query,
        final_brief=answer,
        single_llm_answer="",
        proposals=[],
        refinements=[],
        events=events,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=(finished_at - started_at).total_seconds(),
    )
    yield {"kind": "result", "result": result.model_dump(mode="json")}


async def run_open_query(
    query: str,
    messages: list[dict[str, str]] | None = None,
    date: str | None = None,
    language: str = "en",
) -> RunResult:
    """Run the NBA Copilot tool-using agent and return RunResult."""
    started_at = datetime.now()
    date_value = date or datetime.now().date().isoformat()
    agent, _model_name, model_label, tools = _build_nba_copilot_agent(language)
    input_messages = _build_input_messages(query=query, messages=messages)

    events: list[AgentEvent] = [
        _event("start", f"NBA Copilot started with {len(tools)} MCP tools.", model=model_label)
    ]

    try:
        result = await agent.ainvoke({"messages": input_messages})
        messages: list[BaseMessage] = result.get("messages", [])
        events.extend(_tool_events(messages))
        answer = _final_answer(messages)
        if _tool_uses_bdl_season_averages_401(messages):
            answer += (
                "\n\n> Note: balldontlie season averages are unavailable on the current API plan "
                "(401 Unauthorized), so this answer uses other available data sources."
            )
        events.append(_event("done", "NBA Copilot answer ready.", model=model_label))
    except Exception as exc:
        answer = (
            "I couldn't complete the NBA Copilot run because the LLM call failed.\n\n"
            f"Error: `{exc}`\n\n"
            "Please verify network access / API connectivity and try again."
        )
        events.append(_event("error", f"NBA Copilot failed: {exc}", model=model_label))

    finished_at = datetime.now()
    return RunResult(
        mode="query",
        date=date_value,
        query=query,
        final_brief=answer,
        single_llm_answer="",
        proposals=[],
        refinements=[],
        events=events,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=(finished_at - started_at).total_seconds(),
    )

