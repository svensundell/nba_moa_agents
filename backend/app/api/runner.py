"""Helpers that drive the LangGraph pipeline for each API mode.

Splitting this out of the route handlers keeps the FastAPI layer thin and
lets the WebSocket streamer reuse the same logic with a different sink.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal

from loguru import logger

from app.api.schemas import ProposalView, RefinementView, RunResult
from app.moa.graph import GRAPH
from app.moa.state import AgentEvent, MoAState, initial_state


async def _stream_graph(state: MoAState) -> AsyncIterator[tuple[str, dict]]:
    """Iterate over LangGraph node updates as they arrive.

    Each yield is ``(node_name, partial_state_update)``. We use ``stream_mode="updates"``
    so we get one event per finished node — perfect to forward as WebSocket frames.
    """
    async for chunk in GRAPH.astream(state, stream_mode="updates"):
        for node_name, update in chunk.items():
            yield node_name, update


def _to_run_result(
    *,
    mode: Literal["brief", "query", "compare"],
    state: MoAState,
    started_at: datetime,
) -> RunResult:
    finished_at = datetime.now()
    return RunResult(
        mode=mode,
        date=state.get("date", ""),
        query=state.get("query", ""),
        final_brief=state.get("final_brief", ""),
        single_llm_answer=state.get("single_llm_answer", ""),
        proposals=[
            ProposalView(agent=p.agent, model=p.model, summary=p.summary, sources=p.sources)
            for p in state.get("proposals", [])
        ],
        refinements=[
            RefinementView(agent=r.agent, model=r.model, content=r.content)
            for r in state.get("refinements", [])
        ],
        events=state.get("events", []),
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=(finished_at - started_at).total_seconds(),
    )


async def run_full(
    mode: Literal["brief", "query", "compare"],
    *,
    query: str = "",
    date: str | None = None,
) -> RunResult:
    """Run the graph end-to-end and return the consolidated RunResult."""
    started_at = datetime.now()
    state: MoAState = initial_state(mode, query=query, date=date)
    final_state = await GRAPH.ainvoke(state)
    logger.info(
        f"Pipeline done in {(datetime.now() - started_at).total_seconds():.1f}s "
        f"(mode={mode}, proposals={len(final_state.get('proposals', []))})"
    )
    return _to_run_result(mode=mode, state=final_state, started_at=started_at)


async def run_streaming(
    mode: Literal["brief", "query", "compare"],
    *,
    query: str = "",
    date: str | None = None,
) -> AsyncIterator[dict]:
    """Async iterator yielding JSON-serialisable frames as the pipeline runs.

    Frame schema::

        {"kind": "event", "event": <AgentEvent>}
        {"kind": "node_done", "node": "scores", ...}
        {"kind": "result", "result": <RunResult>}
    """
    started_at = datetime.now()
    state: MoAState = initial_state(mode, query=query, date=date)

    yield {"kind": "started", "at": started_at.isoformat(), "mode": mode}

    accumulated: MoAState = dict(state)  # type: ignore[assignment]

    async for node_name, update in _stream_graph(state):
        # Emit each event from the update (these are the pretty agent logs)
        for ev in update.get("events", []) or []:
            if isinstance(ev, AgentEvent):
                yield {"kind": "event", "event": ev.model_dump(mode="json")}
            else:  # already a dict
                yield {"kind": "event", "event": ev}

        # Apply the update on our local mirror so we can emit a final RunResult
        for k, v in update.items():
            existing = accumulated.get(k)
            if isinstance(existing, list) and isinstance(v, list):
                accumulated[k] = existing + v  # type: ignore[literal-required]
            else:
                accumulated[k] = v  # type: ignore[literal-required]

        yield {"kind": "node_done", "node": node_name}

        # Tiny yield so the websocket flushes
        await asyncio.sleep(0)

    yield {
        "kind": "result",
        "result": _to_run_result(
            mode=mode, state=accumulated, started_at=started_at
        ).model_dump(mode="json"),
    }
