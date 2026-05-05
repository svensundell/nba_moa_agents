"""LangGraph wiring for the NBA Mixture of Agents pipeline.

Topology::

                        ┌──────── kickoff (sets initial events) ────────┐
                        │                                               │
        ┌──────┬──────┬─┴──────┬──────────┬─────────┐                  │
        ▼      ▼      ▼        ▼          ▼         ▼                  │
     scores  news  stats  injuries   social    baseline (compare-only) │
        └──────┴───┬──┴────────┴──────────┘                            │
                   ▼                                                    │
         ┌─────────┴─────────┐                                          │
         ▼                   ▼                                          │
      analyst            narrative                                      │
         └────────┬──────────┘                                          │
                  ▼                                                     │
                editor ◀────────────────────────────────────────────────┘

LangGraph runs nodes that share an incoming edge in parallel, so all five
proposers (and the baseline in compare mode) execute concurrently. This is
what gives the pipeline its real performance edge.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

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


def build_graph():
    """Compile the LangGraph state graph.

    The compiled graph is async-safe and reusable across requests.
    """
    g: StateGraph = StateGraph(MoAState)

    g.add_node("kickoff", kickoff)

    # Layer 1
    g.add_node("scores", scores_agent)
    g.add_node("news", news_agent)
    g.add_node("stats", stats_agent)
    g.add_node("injuries", injuries_agent)
    g.add_node("social", social_agent)

    # Layer 2
    g.add_node("analyst", analyst_agent)
    g.add_node("narrative", narrative_agent)

    # Layer 3
    g.add_node("editor", editor_agent)
    g.add_node("baseline", baseline_agent)

    # Edges
    g.add_edge(START, "kickoff")

    # Fan-out from kickoff to all proposers (and baseline)
    for proposer in ("scores", "news", "stats", "injuries", "social", "baseline"):
        g.add_edge("kickoff", proposer)

    # Layer 1 -> Layer 2 (refiners need all proposals)
    for proposer in ("scores", "news", "stats", "injuries", "social"):
        g.add_edge(proposer, "analyst")
        g.add_edge(proposer, "narrative")

    # Layer 2 -> Layer 3
    g.add_edge("analyst", "editor")
    g.add_edge("narrative", "editor")

    # Baseline runs independently and joins the END
    g.add_edge("baseline", "editor")
    g.add_edge("editor", END)

    return g.compile()


# Singleton — compile once at import time.
GRAPH = build_graph()
