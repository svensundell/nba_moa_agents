"""Base helpers shared by every agent in the MoA graph.

Each agent is a small async function with a uniform signature::

    async def run(state: MoAState) -> dict

It returns a partial state update — LangGraph merges that with the global
state via the channel reducers defined in ``state.py``.

External I/O always goes through ``mcp_invoke`` so the project stays strictly
MCP-driven (no ad-hoc HTTP fallbacks).
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from app.mcp.client import (
    MCPNotInitialised,
    MCPToolMissing,
    _extract_text,
    mcp_registry,
)
from app.moa.llm import AGENT_MODELS, get_model, model_id
from app.moa.state import AgentEvent, AgentProposal


def event(
    agent: str,
    layer: str,
    type_: str,
    *,
    content: str = "",
    model: str = "",
) -> AgentEvent:
    """Convenience constructor for AgentEvent."""
    return AgentEvent(
        agent=agent,
        layer=layer,  # type: ignore[arg-type]
        type=type_,  # type: ignore[arg-type]
        content=content,
        model=model,
    )


# ─── LLM ─────────────────────────────────────────────────────────────────────


async def call_llm(
    agent: str,
    *,
    system: str,
    user: str,
    temperature: float | None = None,
) -> str:
    """Run a one-shot LLM call for an agent and return the text content."""
    model_name = AGENT_MODELS.get(agent, "llama-versatile")
    llm = get_model(model_name, temperature=temperature)
    msgs: list[Any] = [SystemMessage(content=system), HumanMessage(content=user)]
    try:
        response = await llm.ainvoke(msgs)
        return str(response.content).strip()
    except Exception as exc:  # pragma: no cover - network errors
        logger.bind(agent=agent).error(f"LLM call failed: {exc}")
        return f"[error: {agent} LLM call failed: {exc}]"


# ─── MCP tool invocation (with structured event emission) ────────────────────


class MCPToolError(RuntimeError):
    """Wraps any MCP-related failure so callers can convert it to an event."""


async def mcp_invoke(
    agent: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[str, AgentEvent]:
    """Call an MCP tool from inside an agent and return (raw_result, event).

    The caller is expected to add the returned event to its events list and
    decide what to do with the raw result string. A failure is converted to
    an ``MCPToolError`` after producing a structured "error" event so the
    pipeline can record it in the trace.
    """
    try:
        tool = mcp_registry.get_tool(tool_name)
    except (MCPNotInitialised, MCPToolMissing) as exc:
        ev = event(agent, _layer_for(agent), "error", content=f"{tool_name}: {exc}")
        raise MCPToolError(str(exc)) from exc

    try:
        coroutine = getattr(tool, "coroutine", None)
        if coroutine is not None:
            content, _artifact = await coroutine(**arguments)
            text = _extract_text(content)
        else:
            text = _extract_text(await tool.ainvoke(arguments))
    except Exception as exc:  # pragma: no cover - depends on MCP subprocess
        logger.bind(agent=agent).error(f"MCP {tool_name} failed: {exc}")
        ev = event(agent, _layer_for(agent), "error", content=f"{tool_name} failed: {exc}")
        raise MCPToolError(str(exc)) from exc
    preview = text[:160].replace("\n", " ")
    ev = event(
        agent,
        _layer_for(agent),
        "tool",
        content=f"{tool_name}({_args_repr(arguments)}) → {preview}",
    )
    return text, ev


def _args_repr(arguments: dict[str, Any]) -> str:
    if not arguments:
        return ""
    return ", ".join(f"{k}={v!r}" for k, v in arguments.items())


def _layer_for(agent: str) -> str:
    if agent in {"scores", "news", "stats", "injuries", "social"}:
        return "proposer"
    if agent in {"analyst", "narrative"}:
        return "refiner"
    if agent in {"editor", "baseline"}:
        return "aggregator"
    return "system"


def parse_mcp_json(raw: str) -> Any:
    """Parse an MCP tool result string back into a Python object.

    MCP servers return content as JSON-serialised text. We try to decode it,
    falling back to the raw string on parse errors so callers can still
    forward something to the LLM.
    """
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


# ─── Proposal helper ─────────────────────────────────────────────────────────


def make_proposal(
    agent: str,
    summary: str,
    sources: list[str] | None = None,
    raw: str = "",
) -> AgentProposal:
    return AgentProposal(
        agent=agent,
        model=model_id(AGENT_MODELS.get(agent, "llama-versatile")),
        summary=summary,
        sources=sources or [],
        raw=raw,
    )
