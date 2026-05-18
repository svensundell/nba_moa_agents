"""Evaluation module — observable, persisted run metrics.

Exposed surface is intentionally small so callers can stay unaware of the
storage and pricing internals::

    from app.eval import current_tracker, RunTracker

The module turns each pipeline invocation into a row of objective metrics
(cost, latency, tool failures, source coverage) so the system can be
compared across runs, modes, and model lineups.
"""

from app.eval.pricing import cost_usd, price_for_model
from app.eval.schemas import (
    AgentMetrics,
    RunMetrics,
    RunSummary,
    ToolCallMetric,
)
from app.eval.tracker import RunTracker, current_tracker, use_tracker

__all__ = [
    "AgentMetrics",
    "RunMetrics",
    "RunSummary",
    "RunTracker",
    "ToolCallMetric",
    "cost_usd",
    "current_tracker",
    "price_for_model",
    "use_tracker",
]
