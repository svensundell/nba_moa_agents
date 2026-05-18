"""LangGraph wiring for the NBA Mixture of Agents pipeline.

Topology::

                        ┌──────── kickoff (sets initial events) ────────┐
                        │                                               │
        ┌──────┬──────┬─┴──────┬──────────┬─────────┐                  │
        ▼      ▼      ▼        ▼          ▼         ▼                  │
     scores  news  stats  injuries   social    baseline (compare-only) │
        └──────┴───┬──┴────────┴──────────┘                            │
                   ▼                                                    ▼
         ┌─────────┴─────────┐                                         END
         ▼                   ▼
      analyst            narrative
         └────────┬──────────┘
                  ▼
                editor

LangGraph runs nodes that share an incoming edge in parallel, so all five
proposers (and the baseline in compare mode) execute concurrently. This is
what gives the pipeline its real performance edge.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.eval import current_tracker
from app.moa.agents.base import event
from app.moa.agents.editor import baseline_agent, editor_agent
from app.moa.agents.proposers import (
    injuries_agent,
    news_agent,
    scores_agent,
    social_agent,
    stats_agent,
)
from app.moa.agents.refiners import analyst_agent, narrative_agent
from app.moa.state import MoAState

NodeFn = Callable[[MoAState], Awaitable[dict[str, Any]]]


def _track(name: str, fn: NodeFn) -> NodeFn:
    """Wrap a LangGraph node with per-agent wall-clock timing.

    The wrapper is a no-op when no tracker is bound to the current task,
    so the function stays safe to call from CLI / unit-test contexts.
    """

    async def wrapped(state: MoAState) -> dict[str, Any]:
        tracker = current_tracker()
        if tracker is None:
            return await fn(state)
        async with tracker.time_agent(name):
            return await fn(state)

    wrapped.__name__ = f"tracked_{name}"
    return wrapped


async def kickoff(state: MoAState) -> dict:
    """Trivial entry node — emits a 'system started' event for the UI."""
    return {
        "events": [
            event(
                agent="system",
                layer="system",
                type_="start",
                content=f"Starting MoA pipeline (mode={state.get('mode')})",
            )
        ]
    }


def _next_nodes_after_kickoff(state: MoAState) -> list[str]:
    """Route baseline only in compare mode."""
    proposers = ["scores", "news", "stats", "injuries", "social"]
    if state.get("mode") == "compare":
        return [*proposers, "baseline"]
    return proposers


def build_graph():
    """Compile the LangGraph state graph.

    The compiled graph is async-safe and reusable across requests.
    """
    g: StateGraph = StateGraph(MoAState)

    g.add_node("kickoff", _track("kickoff", kickoff))

    # Layer 1
    g.add_node("scores", _track("scores", scores_agent))
    g.add_node("news", _track("news", news_agent))
    g.add_node("stats", _track("stats", stats_agent))
    g.add_node("injuries", _track("injuries", injuries_agent))
    g.add_node("social", _track("social", social_agent))

    # Layer 2
    g.add_node("analyst", _track("analyst", analyst_agent))
    g.add_node("narrative", _track("narrative", narrative_agent))

    # Layer 3
    g.add_node("editor", _track("editor", editor_agent))
    g.add_node("baseline", _track("baseline", baseline_agent))

    # Edges
    g.add_edge(START, "kickoff")

    # Fan-out from kickoff. Baseline runs only in compare mode.
    g.add_conditional_edges("kickoff", _next_nodes_after_kickoff)

    # Layer 1 -> Layer 2 (explicit barriers: refiners wait for all proposers)
    proposers = ["scores", "news", "stats", "injuries", "social"]
    g.add_edge(proposers, "analyst")
    g.add_edge(proposers, "narrative")

    # Layer 2 -> Layer 3 (barrier: wait for BOTH refiners)
    g.add_edge(["analyst", "narrative"], "editor")

    # Baseline stays independent; it should never trigger editor.
    g.add_edge("baseline", END)
    g.add_edge("editor", END)

    return g.compile()


# Singleton — compile once at import time.
GRAPH = build_graph()
