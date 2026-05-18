"""Helpers that drive the LangGraph pipeline for each API mode.

Splitting this out of the route handlers keeps the FastAPI layer thin and
lets the WebSocket streamer reuse the same logic with a different sink.

This module is also the single place where:

* A :class:`~app.eval.RunTracker` is created and bound to the current
  task, so every nested LLM / MCP call is automatically observed.
* The finalised :class:`~app.eval.RunMetrics` are persisted to SQLite via
  :class:`~app.eval.repository.EvalRepository`, and attached to the
  :class:`~app.api.schemas.RunResult` returned to the caller.

Agents themselves never see the tracker — they only get instrumented by
the helpers in ``app.moa.agents.base``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal

from loguru import logger

from app.api.schemas import ProposalView, RefinementView, RunResult
from app.eval import RunTracker, use_tracker
from app.eval.repository import get_repository
from app.eval.schemas import RunMetrics
from app.moa.graph import GRAPH
from app.moa.open_query import run_open_query, stream_open_query_frames
from app.moa.state import AgentEvent, AgentProposal, MoAState, initial_state


async def _stream_graph(state: MoAState) -> AsyncIterator[tuple[str, dict]]:
    """Iterate over LangGraph node updates as they arrive.

    Each yield is ``(node_name, partial_state_update)``. We use
    ``stream_mode="updates"`` so we get one event per finished node —
    perfect to forward as WebSocket frames.
    """
    async for chunk in GRAPH.astream(state, stream_mode="updates"):
        for node_name, update in chunk.items():
            yield node_name, update


def _record_sources(tracker: RunTracker, state: MoAState) -> None:
    """Push the proposals' citations into the tracker."""
    proposals = state.get("proposals", []) or []
    typed_proposals: list[AgentProposal] = []
    for p in proposals:
        if isinstance(p, AgentProposal):
            typed_proposals.append(p)
    if typed_proposals:
        tracker.add_proposal_sources(typed_proposals)


def _to_run_result(
    *,
    mode: Literal["brief", "query", "compare"],
    state: MoAState,
    started_at: datetime,
    metrics: RunMetrics | None = None,
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
        metrics=metrics,
    )


async def _persist_run(
    *,
    metrics: RunMetrics,
    result: RunResult,
    language: str,
) -> None:
    """Best-effort write to the eval repository.

    A persistence failure must never break the user-visible pipeline, so
    errors are logged and swallowed. The metrics are still attached to
    the in-memory ``RunResult`` returned to the caller.
    """
    try:
        repo = get_repository()
    except RuntimeError:
        return
    try:
        await repo.save_run(
            metrics=metrics,
            date=result.date,
            query=result.query,
            language=language,
            final_brief=result.final_brief,
            single_llm_answer=result.single_llm_answer,
            payload=result.model_dump(mode="json"),
        )
    except Exception as exc:  # pragma: no cover - depends on SQLite
        logger.error(f"Failed to persist run {metrics.run_id}: {exc}")


async def run_full(
    mode: Literal["brief", "query", "compare"],
    *,
    query: str = "",
    messages: list[dict[str, str]] | None = None,
    date: str | None = None,
    language: Literal["en", "fr"] = "en",
) -> RunResult:
    """Run the graph end-to-end and return the consolidated RunResult."""
    tracker = RunTracker(mode=mode)
    started_at = datetime.now()
    with use_tracker(tracker):
        if mode == "query":
            result = await run_open_query(
                query=query,
                messages=messages,
                date=date,
                language=language,
            )
        else:
            state: MoAState = initial_state(
                mode, query=query, date=date, language=language
            )
            final_state = await GRAPH.ainvoke(state)
            logger.info(
                f"Pipeline done in {(datetime.now() - started_at).total_seconds():.1f}s "
                f"(mode={mode}, proposals={len(final_state.get('proposals', []))})"
            )
            _record_sources(tracker, final_state)
            result = _to_run_result(mode=mode, state=final_state, started_at=started_at)

    metrics = tracker.finalize()
    result.metrics = metrics
    await _persist_run(metrics=metrics, result=result, language=language)
    return result


async def run_streaming(
    mode: Literal["brief", "query", "compare"],
    *,
    query: str = "",
    messages: list[dict[str, str]] | None = None,
    date: str | None = None,
    language: Literal["en", "fr"] = "en",
) -> AsyncIterator[dict]:
    """Async iterator yielding JSON-serialisable frames as the pipeline runs.

    Frame schema::

        {"kind": "event", "event": <AgentEvent>}
        {"kind": "node_done", "node": "scores", ...}
        {"kind": "result", "result": <RunResult>}
    """
    tracker = RunTracker(mode=mode)
    with use_tracker(tracker):
        if mode == "query":
            final_result: RunResult | None = None
            async for frame in stream_open_query_frames(
                query=query,
                messages=messages,
                date=date,
                language=language,
            ):
                if frame.get("kind") == "result":
                    final_result = RunResult.model_validate(frame["result"])
                    metrics = tracker.finalize()
                    final_result.metrics = metrics
                    frame = {
                        "kind": "result",
                        "result": final_result.model_dump(mode="json"),
                    }
                yield frame
            if final_result is not None:
                await _persist_run(
                    metrics=final_result.metrics or tracker.finalize(),
                    result=final_result,
                    language=language,
                )
            return

        started_at = datetime.now()
        state: MoAState = initial_state(mode, query=query, date=date, language=language)

        yield {"kind": "started", "at": started_at.isoformat(), "mode": mode}

        accumulated: MoAState = dict(state)  # type: ignore[assignment]

        async for node_name, update in _stream_graph(state):
            for ev in update.get("events", []) or []:
                if isinstance(ev, AgentEvent):
                    yield {"kind": "event", "event": ev.model_dump(mode="json")}
                else:  # already a dict
                    yield {"kind": "event", "event": ev}

            for k, v in update.items():
                existing = accumulated.get(k)
                if isinstance(existing, list) and isinstance(v, list):
                    accumulated[k] = existing + v  # type: ignore[literal-required]
                else:
                    accumulated[k] = v  # type: ignore[literal-required]

            yield {"kind": "node_done", "node": node_name}
            await asyncio.sleep(0)

        _record_sources(tracker, accumulated)
        metrics = tracker.finalize()
        result = _to_run_result(
            mode=mode,
            state=accumulated,
            started_at=started_at,
            metrics=metrics,
        )
        yield {
            "kind": "result",
            "result": result.model_dump(mode="json"),
        }
        await _persist_run(metrics=metrics, result=result, language=language)
