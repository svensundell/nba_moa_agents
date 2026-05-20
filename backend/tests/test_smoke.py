"""Smoke tests — they don't hit any LLM and they don't initialise MCP.

We just check that imports are clean, the LangGraph compiles, the agent ↔
model mapping is consistent, and the MCP registry advertises the three
expected servers.
"""

from __future__ import annotations

from pathlib import Path


def test_imports() -> None:
    from app.moa.graph import GRAPH
    from app.moa.state import initial_state

    state = initial_state("brief")
    assert state["mode"] == "brief"
    assert state["proposals"] == []
    assert GRAPH is not None


def test_agent_model_assignments_have_valid_specs() -> None:
    from app.moa.llm import AGENT_MODELS, MODEL_REGISTRY

    for agent, logical in AGENT_MODELS.items():
        assert logical in MODEL_REGISTRY, f"{agent} maps to unknown model {logical}"


def test_graph_nodes_present() -> None:
    from app.moa.graph import GRAPH

    expected = {
        "kickoff",
        "scores",
        "news",
        "stats",
        "injuries",
        "social",
        "analyst",
        "narrative",
        "editor",
    }
    nodes = set(GRAPH.get_graph().nodes.keys())
    missing = expected - nodes
    assert not missing, f"Missing graph nodes: {missing}"


def test_mcp_registry_lists_three_servers() -> None:
    from app.mcp.client import SERVER_PATHS, mcp_registry

    assert set(mcp_registry.server_names) == {"nba_stats", "reddit", "espn"}
    for path in SERVER_PATHS.values():
        assert isinstance(path, Path)
        assert path.exists(), f"Missing MCP server entrypoint: {path}"


def test_no_data_sources_module() -> None:
    """Ensure the deprecated HTTP fallback module is gone for good."""
    from importlib import util

    spec = util.find_spec("app.moa.agents.data_sources")
    assert spec is None, "app.moa.agents.data_sources should no longer exist"
