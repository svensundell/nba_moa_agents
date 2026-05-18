"""Pydantic schemas for the evaluation module.

Three layers of detail are exposed so the frontend can pick the right one:

* :class:`RunSummary` — one row per persisted run (list views).
* :class:`RunMetrics` — the live numbers attached to every ``RunResult``.
* :class:`AgentMetrics` / :class:`ToolCallMetric` — per-agent / per-call
  breakdown shown on the run detail and dashboard pages.

Keeping these in a dedicated module avoids a circular import between
``app.api.schemas`` and ``app.eval.tracker``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RunMode = Literal["brief", "query", "compare"]


class SourceCitation(BaseModel):
    """One auditable data source used during a pipeline run."""

    id: int
    provider: str
    tool: str
    agent: str
    retrieved_at: datetime
    url: str | None = None
    title: str = ""
    excerpt: str = ""


class ToolCallMetric(BaseModel):
    """One MCP tool invocation recorded by the tracker."""

    agent: str
    tool: str
    latency_ms: float
    success: bool
    error: str | None = None
    started_at: datetime


class AgentMetrics(BaseModel):
    """All measurements bucketed by the agent that produced them."""

    agent: str
    model: str = ""
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    llm_latency_ms: float = 0.0
    tool_calls: int = 0
    tool_failures: int = 0
    tool_latency_ms: float = 0.0
    wall_clock_ms: float = 0.0


class RunMetrics(BaseModel):
    """Top-level metrics attached to every ``RunResult``.

    The MoA pipeline and the NBA Copilot agent both populate the same
    shape so the dashboard can chart them on equal footing.
    """

    run_id: str
    mode: RunMode
    started_at: datetime
    finished_at: datetime
    duration_seconds: float

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    llm_call_count: int = 0

    tool_call_count: int = 0
    tool_failure_count: int = 0

    distinct_sources: int = 0
    sources: list[str] = Field(default_factory=list)

    agents: list[AgentMetrics] = Field(default_factory=list)
    tool_calls: list[ToolCallMetric] = Field(default_factory=list)

    # For compare mode only: the cost split between the MoA editor pipeline
    # and the single-LLM baseline, so the dashboard can show the ratio.
    moa_cost_usd: float = 0.0
    baseline_cost_usd: float = 0.0

    estimated_price: bool = False


class RunSummary(BaseModel):
    """One row in the run history table."""

    run_id: str
    mode: RunMode
    date: str
    query: str = ""
    language: Literal["en", "fr"] = "en"
    started_at: datetime
    duration_seconds: float
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    llm_call_count: int
    tool_call_count: int
    tool_failure_count: int
    distinct_sources: int
    moa_cost_usd: float = 0.0
    baseline_cost_usd: float = 0.0
    estimated_price: bool = False


class DashboardSummary(BaseModel):
    """Aggregates rendered on the dashboard landing card."""

    total_runs: int
    avg_cost_usd: float
    avg_duration_seconds: float
    tool_failure_rate: float
    cost_by_mode: dict[str, float]
    avg_cost_by_mode: dict[str, float]
    runs_by_mode: dict[str, int]
    compare_avg_moa_cost_usd: float
    compare_avg_baseline_cost_usd: float
    p95_duration_seconds: float
    last_run_at: datetime | None = None
