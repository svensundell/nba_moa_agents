"""LangGraph workflow tests — structure only, no LLM or MCP subprocess."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("mode", ["brief", "compare", "query"])
def test_initial_state_mode(mode: str) -> None:
    from app.moa.state import initial_state

    state = initial_state(mode)  # type: ignore[arg-type]
    assert state["mode"] == mode
    assert state["proposals"] == []
    assert state["events"] == []


def test_compare_mode_includes_baseline_node() -> None:
    from app.moa.graph import GRAPH

    nodes = set(GRAPH.get_graph().nodes.keys())
    assert "baseline" in nodes


def test_brief_graph_edges_from_kickoff() -> None:
    from app.moa.graph import GRAPH

    g = GRAPH.get_graph()
    # Layer-1 proposers fan out from kickoff in parallel.
    for proposer in ("scores", "news", "stats", "injuries", "social"):
        assert proposer in g.nodes
    assert "editor" in g.nodes
    assert "analyst" in g.nodes
    assert "narrative" in g.nodes
