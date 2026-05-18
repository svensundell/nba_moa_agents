"""Per-run metrics collector wired in through a ContextVar.

Design goals
------------

* **Implicit propagation**: agents that already use ``call_llm`` and
  ``mcp_invoke`` get instrumented automatically. They never see the
  tracker. The two tool-using agents (``stats`` and ``nba_copilot``) call
  ``current_tracker()`` explicitly because they bypass ``call_llm`` and
  read token usage out of ``astream_events``.
* **Process-local & async-safe**: a :class:`contextvars.ContextVar`
  scopes the tracker to one in-flight request/run. FastAPI handlers run
  in their own task, so cross-request bleed is impossible.
* **Side-effect free at import time**: nothing touches the filesystem or
  the network. Persistence is a separate module (``repository``).

The tracker accumulates four things:

1. LLM usage per ``(agent, model_id)``: count, tokens, latency, cost.
2. MCP tool calls per ``(agent, tool)``: count, latency, success, error.
3. Wall-clock time per agent (set by a context-manager wrapping the
   LangGraph node).
4. Source citations seen across the run (deduplicated).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Iterable, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from app.eval.pricing import cost_usd as compute_cost_usd
from app.eval.pricing import price_for_model
from app.eval.schemas import AgentMetrics, RunMetrics, SourceCitation, ToolCallMetric
from app.moa.citations import citation_from_mcp, urls_from_payload

if TYPE_CHECKING:
    from app.moa.state import AgentProposal


RunMode = Literal["brief", "query", "compare"]


class RunTracker:
    """Accumulates evaluation metrics for one pipeline invocation.

    A new instance is created per HTTP / WebSocket request and bound to
    the current task's :data:`_current_tracker` ContextVar via
    :func:`use_tracker`.
    """

    def __init__(self, *, mode: RunMode) -> None:
        self.run_id: str = uuid.uuid4().hex
        self.mode: RunMode = mode
        self.started_at: datetime = datetime.now()
        self._monotonic_start: float = time.monotonic()
        self._agents: dict[str, AgentMetrics] = {}
        self._tool_calls: list[ToolCallMetric] = []
        self._sources: set[str] = set()
        self._citations: list[SourceCitation] = []
        self._citation_seq: int = 0
        self._estimated_price: bool = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _agent(self, agent: str, *, model: str = "") -> AgentMetrics:
        """Get or create the :class:`AgentMetrics` row for ``agent``.

        ``model`` is recorded the first time it's seen so the dashboard
        can label per-agent rows. Subsequent calls keep the earlier
        value, which is what we want for sub-agents that use one model.
        """
        row = self._agents.get(agent)
        if row is None:
            row = AgentMetrics(agent=agent, model=model)
            self._agents[agent] = row
        elif model and not row.model:
            row.model = model
        return row

    # ------------------------------------------------------------------
    # Recording APIs
    # ------------------------------------------------------------------

    def record_llm_call(
        self,
        *,
        agent: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
    ) -> None:
        """Record one LLM call worth of tokens, latency and (priced) cost."""
        price = price_for_model(model_id)
        if price.estimated:
            self._estimated_price = True
        cost = compute_cost_usd(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_id=model_id,
        )
        row = self._agent(agent, model=model_id)
        row.llm_calls += 1
        row.input_tokens += max(0, int(input_tokens))
        row.output_tokens += max(0, int(output_tokens))
        row.cost_usd += cost
        row.llm_latency_ms += max(0.0, latency_ms)

    def record_tool_call(
        self,
        *,
        agent: str,
        tool: str,
        latency_ms: float,
        success: bool,
        error: str | None = None,
        started_at: datetime | None = None,
    ) -> None:
        """Record one MCP tool invocation."""
        row = self._agent(agent)
        row.tool_calls += 1
        row.tool_latency_ms += max(0.0, latency_ms)
        if not success:
            row.tool_failures += 1
        self._tool_calls.append(
            ToolCallMetric(
                agent=agent,
                tool=tool,
                latency_ms=max(0.0, latency_ms),
                success=success,
                error=error,
                started_at=started_at or datetime.now(),
            )
        )

    def record_agent_wall_clock(self, agent: str, latency_ms: float) -> None:
        """Record the wall-clock time spent inside an agent's node."""
        row = self._agent(agent)
        row.wall_clock_ms += max(0.0, latency_ms)

    def add_sources(self, sources: Iterable[str]) -> None:
        """Record source citations (dedup later via ``set`` semantics)."""
        for src in sources:
            if src:
                self._sources.add(src)

    def list_citations(self) -> list[SourceCitation]:
        """Structured citations recorded via :meth:`record_mcp_citation`."""
        return list(self._citations)

    def record_mcp_citation(
        self,
        *,
        agent: str,
        tool_name: str,
        raw_text: str,
        retrieved_at: datetime,
        arguments: dict[str, Any] | None = None,
    ) -> SourceCitation:
        """Register one MCP tool result as a numbered source citation."""
        self._citation_seq += 1
        cite = citation_from_mcp(
            citation_id=self._citation_seq,
            agent=agent,
            tool_name=tool_name,
            raw_text=raw_text,
            retrieved_at=retrieved_at,
            arguments=arguments,
        )
        self._citations.append(cite)
        self._sources.add(f"mcp:{tool_name}")
        for url in urls_from_payload(raw_text):
            self._sources.add(url)
        return cite

    def add_proposal_sources(self, proposals: Iterable[AgentProposal]) -> None:
        """Convenience: extract source strings from a proposals list."""
        self.add_sources(s for p in proposals for s in (p.sources or []))

    # ------------------------------------------------------------------
    # Context managers (timing helpers)
    # ------------------------------------------------------------------

    @contextmanager
    def time_llm(
        self,
        *,
        agent: str,
        model_id: str,
    ) -> Iterator[_LLMTimer]:
        """Time a single LLM call and record its usage on exit.

        The yielded object exposes ``set_usage(input, output)`` so the
        caller can attach token counts from the response payload.
        """
        timer = _LLMTimer()
        start = time.monotonic()
        try:
            yield timer
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000.0
            self.record_llm_call(
                agent=agent,
                model_id=model_id,
                input_tokens=timer.input_tokens,
                output_tokens=timer.output_tokens,
                latency_ms=elapsed_ms,
            )

    @asynccontextmanager
    async def time_agent(self, agent: str) -> AsyncIterator[None]:
        """Wrap a LangGraph node and add the elapsed time to its row."""
        start = time.monotonic()
        try:
            yield
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000.0
            self.record_agent_wall_clock(agent, elapsed_ms)

    # ------------------------------------------------------------------
    # Finalisation
    # ------------------------------------------------------------------

    def finalize(self) -> RunMetrics:
        """Freeze the tracker into an immutable :class:`RunMetrics`."""
        finished_at = datetime.now()
        elapsed_s = time.monotonic() - self._monotonic_start

        total_input = 0
        total_output = 0
        total_cost = 0.0
        llm_calls = 0
        tool_calls = 0
        tool_failures = 0
        moa_cost = 0.0
        baseline_cost = 0.0

        for row in self._agents.values():
            total_input += row.input_tokens
            total_output += row.output_tokens
            total_cost += row.cost_usd
            llm_calls += row.llm_calls
            tool_calls += row.tool_calls
            tool_failures += row.tool_failures
            # Compare mode: split MoA pipeline cost vs single-LLM baseline.
            if row.agent in {"single_llm_baseline", "baseline"}:
                baseline_cost += row.cost_usd
            else:
                moa_cost += row.cost_usd

        return RunMetrics(
            run_id=self.run_id,
            mode=self.mode,
            started_at=self.started_at,
            finished_at=finished_at,
            duration_seconds=elapsed_s,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_cost_usd=round(total_cost, 6),
            llm_call_count=llm_calls,
            tool_call_count=tool_calls,
            tool_failure_count=tool_failures,
            distinct_sources=len(self._sources),
            sources=sorted(self._sources),
            agents=sorted(self._agents.values(), key=lambda a: a.agent),
            tool_calls=list(self._tool_calls),
            moa_cost_usd=round(moa_cost, 6),
            baseline_cost_usd=round(baseline_cost, 6),
            estimated_price=self._estimated_price,
        )


class _LLMTimer:
    """Tiny payload returned by :meth:`RunTracker.time_llm`.

    Lives only for the duration of one ``with`` block. The agent code
    fills it in via ``set_usage(...)`` once it has the response.
    """

    __slots__ = ("input_tokens", "output_tokens")

    def __init__(self) -> None:
        self.input_tokens: int = 0
        self.output_tokens: int = 0

    def set_usage(self, input_tokens: int | None, output_tokens: int | None) -> None:
        self.input_tokens = int(input_tokens or 0)
        self.output_tokens = int(output_tokens or 0)


# ---------------------------------------------------------------------------
# ContextVar plumbing
# ---------------------------------------------------------------------------

_current_tracker: ContextVar[RunTracker | None] = ContextVar(
    "nba_moa_run_tracker", default=None
)


def current_tracker() -> RunTracker | None:
    """Return the tracker bound to the current task, if any."""
    return _current_tracker.get()


@contextmanager
def use_tracker(tracker: RunTracker) -> Iterator[RunTracker]:
    """Bind ``tracker`` to the current task for the duration of the block.

    Restores the previous value on exit so nested usage is well-defined.
    """
    token = _current_tracker.set(tracker)
    try:
        yield tracker
    finally:
        _current_tracker.reset(token)
