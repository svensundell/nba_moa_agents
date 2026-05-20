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
import re
import time
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from loguru import logger

from app.eval import current_tracker
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
    citation_id: int | None = None,
    provider: str | None = None,
    tool: str | None = None,
    retrieved_at: datetime | None = None,
    source_url: str | None = None,
) -> AgentEvent:
    """Convenience constructor for AgentEvent."""
    return AgentEvent(
        agent=agent,
        layer=layer,  # type: ignore[arg-type]
        type=type_,  # type: ignore[arg-type]
        content=content,
        model=model,
        citation_id=citation_id,
        provider=provider,
        tool=tool,
        retrieved_at=retrieved_at,
        source_url=source_url,
    )


# ─── LLM ─────────────────────────────────────────────────────────────────────


def _usage_from_response(response: Any) -> tuple[int, int]:
    """Best-effort extraction of (input_tokens, output_tokens) from an LLM response.

    LangChain's ``ChatOpenAI`` populates ``usage_metadata`` on the
    returned ``AIMessage`` for OpenAI-compatible providers. OpenRouter is
    OpenAI-compatible, so we read it from there first. ``response_metadata``
    is checked as a fallback for older versions.
    """
    if isinstance(response, AIMessage):
        usage = getattr(response, "usage_metadata", None)
        if isinstance(usage, dict):
            return (
                int(usage.get("input_tokens", 0) or 0),
                int(usage.get("output_tokens", 0) or 0),
            )
    meta = getattr(response, "response_metadata", None)
    if isinstance(meta, dict):
        token_usage = meta.get("token_usage") or meta.get("usage") or {}
        if isinstance(token_usage, dict):
            return (
                int(token_usage.get("prompt_tokens") or token_usage.get("input_tokens") or 0),
                int(token_usage.get("completion_tokens") or token_usage.get("output_tokens") or 0),
            )
    return 0, 0


async def call_llm(
    agent: str,
    *,
    system: str,
    user: str,
    temperature: float | None = None,
) -> str:
    """Run a one-shot LLM call for an agent and return the text content.

    LLM latency, token usage and (priced) cost are recorded on the
    :class:`~app.eval.RunTracker` bound to the current task, when one is
    present. Agent code stays oblivious to instrumentation.
    """
    model_name = AGENT_MODELS.get(agent, "balanced")
    resolved_model = model_id(model_name)
    llm = get_model(model_name, temperature=temperature)
    msgs: list[Any] = [SystemMessage(content=system), HumanMessage(content=user)]

    tracker = current_tracker()
    start = time.monotonic()
    try:
        response = await llm.ainvoke(msgs)
    except Exception as exc:  # pragma: no cover - network errors
        if tracker is not None:
            tracker.record_llm_call(
                agent=agent,
                model_id=resolved_model,
                input_tokens=0,
                output_tokens=0,
                latency_ms=(time.monotonic() - start) * 1000.0,
            )
        logger.bind(agent=agent).error(
            f"LLM call failed (logical={model_name}, resolved={resolved_model}): {exc}"
        )
        return (
            f"[error: {agent} LLM call failed "
            f"(logical={model_name}, resolved={resolved_model}): {exc}]"
        )

    if tracker is not None:
        in_tok, out_tok = _usage_from_response(response)
        tracker.record_llm_call(
            agent=agent,
            model_id=resolved_model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=(time.monotonic() - start) * 1000.0,
        )
    return str(response.content).strip()


# ─── MCP tool invocation (with structured event emission) ────────────────────


class MCPToolError(RuntimeError):
    """Wraps any MCP-related failure so callers can convert it to an event."""


async def mcp_invoke(
    agent: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[str, AgentEvent]:
    """Call an MCP tool from inside an agent and return (raw_result, event).

    Latency and success/failure of every call are recorded on the active
    :class:`~app.eval.RunTracker` when one is bound — including the
    failure path so the dashboard can compute tool failure rates.
    """
    tracker = current_tracker()
    started_at = datetime.now()
    start = time.monotonic()

    def _record(success: bool, error: str | None = None) -> None:
        if tracker is None:
            return
        tracker.record_tool_call(
            agent=agent,
            tool=tool_name,
            latency_ms=(time.monotonic() - start) * 1000.0,
            success=success,
            error=error,
            started_at=started_at,
        )

    try:
        tool = mcp_registry.get_tool(tool_name)
    except (MCPNotInitialised, MCPToolMissing) as exc:
        _record(False, str(exc))
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
        _record(False, str(exc))
        logger.bind(agent=agent).error(f"MCP {tool_name} failed: {exc}")
        ev = event(agent, _layer_for(agent), "error", content=f"{tool_name} failed: {exc}")
        raise MCPToolError(str(exc)) from exc
    _record(True)
    cite = None
    if tracker is not None:
        cite = tracker.record_mcp_citation(
            agent=agent,
            tool_name=tool_name,
            raw_text=text,
            retrieved_at=started_at,
            arguments=arguments,
        )
    preview = text[:160].replace("\n", " ")
    ev = event(
        agent,
        _layer_for(agent),
        "tool",
        content=f"{tool_name}({_args_repr(arguments)}) → {preview}",
        citation_id=cite.id if cite else None,
        provider=cite.provider if cite else None,
        tool=cite.tool if cite else None,
        retrieved_at=cite.retrieved_at if cite else None,
        source_url=cite.url if cite else None,
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
    if agent == "editor":
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


# ─── Stream event accounting helpers ─────────────────────────────────────────


def record_streamed_llm_call(
    agent: str,
    model_id_label: str,
    trace_event: dict[str, Any],
    *,
    fallback_latency_ms: float = 0.0,
) -> None:
    """Record an LLM call observed inside ``astream_events``.

    The two tool-using agents (``stats`` and ``nba_copilot``) drive
    LangChain's ``create_agent`` and read tool outputs from the v2 stream.
    Hooking ``on_chat_model_end`` here lets us account for every model
    turn the planner takes without intercepting the runnable.

    ``trace_event`` is one ``astream_events(version="v2")`` payload of
    type ``on_chat_model_end``. We pull token usage from the emitted
    ``AIMessage`` in ``data.output``.
    """
    tracker = current_tracker()
    if tracker is None:
        return
    output = trace_event.get("data", {}).get("output")
    in_tok = 0
    out_tok = 0
    if isinstance(output, AIMessage):
        in_tok, out_tok = _usage_from_response(output)
    elif isinstance(output, dict):
        usage = output.get("usage_metadata") or output.get("usage") or {}
        if isinstance(usage, dict):
            in_tok = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
            out_tok = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    tracker.record_llm_call(
        agent=agent,
        model_id=model_id_label,
        input_tokens=in_tok,
        output_tokens=out_tok,
        latency_ms=max(0.0, fallback_latency_ms),
    )


def sources_from_tool_output(tool_name: str, text: str) -> list[str]:
    """Derive citation strings from an MCP tool result (NBA Copilot path)."""
    sources: list[str] = [f"mcp:{tool_name}"]
    if not text:
        return sources

    for url in re.findall(r"https?://[^\s\"'<>\\]+", text):
        cleaned = url.rstrip(".,);]")
        if cleaned and cleaned not in sources:
            sources.append(cleaned)

    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return sources

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            link = node.get("link") or node.get("url")
            if isinstance(link, str) and link.startswith("http") and link not in sources:
                sources.append(link)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return sources


def record_streamed_tool_call(
    agent: str,
    trace_event: dict[str, Any],
    *,
    started_at: datetime | None = None,
    latency_ms: float = 0.0,
) -> None:
    """Record an MCP tool call observed inside ``astream_events``.

    Mirrors :func:`record_streamed_llm_call` for ``on_tool_end`` events
    so token-using agents still feed the tracker with tool metrics even
    though they bypass :func:`mcp_invoke`.
    """
    tracker = current_tracker()
    if tracker is None:
        return
    tool_name = str(trace_event.get("name", "tool"))
    output = trace_event.get("data", {}).get("output")
    text = ""
    if isinstance(output, str):
        text = output
    elif hasattr(output, "content"):
        text = str(getattr(output, "content", "") or "")
    success = not text.startswith("[error]")
    tracker.record_tool_call(
        agent=agent,
        tool=tool_name,
        latency_ms=latency_ms,
        success=success,
        error=None if success else text[:200],
        started_at=started_at or datetime.now(),
    )
    if success and tool_name != "search_brief_memory":
        tracker.record_mcp_citation(
            agent=agent,
            tool_name=tool_name,
            raw_text=text,
            retrieved_at=started_at or datetime.now(),
        )


# ─── Proposal helper ─────────────────────────────────────────────────────────


def make_proposal(
    agent: str,
    summary: str,
    sources: list[str] | None = None,
    raw: str = "",
) -> AgentProposal:
    return AgentProposal(
        agent=agent,
        model=model_id(AGENT_MODELS.get(agent, "balanced")),
        summary=summary,
        sources=sources or [],
        raw=raw,
    )
