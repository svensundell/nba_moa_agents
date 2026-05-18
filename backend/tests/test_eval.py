"""Unit tests for the evaluation module.

The tests are fully offline:

* pricing math is deterministic
* the tracker is pure Python
* the repository uses a tmp_path-scoped SQLite file

They are intentionally small — one assertion per behaviour — to make
failure messages obvious in CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.eval.pricing import DEFAULT_PRICE, PRICES, cost_usd, price_for_model
from app.eval.repository import EvalRepository
from app.eval.schemas import AgentMetrics, ToolCallMetric
from app.eval.tracker import RunTracker, current_tracker, use_tracker

# ─── Pricing ────────────────────────────────────────────────────────────────


def test_price_for_known_model_uses_registry() -> None:
    p = price_for_model("deepseek/deepseek-chat-v3.1")
    assert p == PRICES["deepseek/deepseek-chat-v3.1"]
    assert p.estimated is False


def test_price_for_unknown_model_falls_back_to_default() -> None:
    p = price_for_model("does/not/exist")
    assert p == DEFAULT_PRICE
    assert p.estimated is True


def test_cost_usd_matches_manual_computation() -> None:
    # 1 000 prompt tokens @ $0.075/1M + 500 completion tokens @ $0.30/1M
    expected = 1_000 * 0.075 / 1_000_000 + 500 * 0.30 / 1_000_000
    actual = cost_usd(
        input_tokens=1_000,
        output_tokens=500,
        model_id="google/gemini-2.5-flash",
    )
    assert actual == pytest.approx(expected, rel=1e-9)


def test_cost_usd_clamps_negative_tokens() -> None:
    assert cost_usd(input_tokens=-5, output_tokens=-10, model_id="any") == 0.0


# ─── Tracker ────────────────────────────────────────────────────────────────


def test_tracker_aggregates_llm_calls_per_agent_and_model() -> None:
    t = RunTracker(mode="brief")
    t.record_llm_call(
        agent="scores",
        model_id="google/gemini-2.5-flash",
        input_tokens=100,
        output_tokens=50,
        latency_ms=200,
    )
    t.record_llm_call(
        agent="scores",
        model_id="google/gemini-2.5-flash",
        input_tokens=200,
        output_tokens=100,
        latency_ms=300,
    )
    metrics = t.finalize()
    assert metrics.llm_call_count == 2
    assert metrics.total_input_tokens == 300
    assert metrics.total_output_tokens == 150
    scores = next(a for a in metrics.agents if a.agent == "scores")
    assert scores.model == "google/gemini-2.5-flash"
    assert scores.llm_calls == 2
    assert scores.llm_latency_ms == 500


def test_tracker_records_tool_failures() -> None:
    t = RunTracker(mode="brief")
    t.record_tool_call(
        agent="news",
        tool="espn_nba_headlines",
        latency_ms=100,
        success=True,
    )
    t.record_tool_call(
        agent="news",
        tool="espn_nba_headlines",
        latency_ms=50,
        success=False,
        error="timeout",
    )
    metrics = t.finalize()
    assert metrics.tool_call_count == 2
    assert metrics.tool_failure_count == 1
    assert len(metrics.tool_calls) == 2
    assert metrics.tool_calls[1].error == "timeout"


def test_tracker_splits_moa_and_baseline_costs_in_compare_mode() -> None:
    t = RunTracker(mode="compare")
    t.record_llm_call(
        agent="editor",
        model_id="deepseek/deepseek-chat-v3.1",
        input_tokens=10_000,
        output_tokens=1_000,
        latency_ms=1_000,
    )
    t.record_llm_call(
        agent="single_llm_baseline",
        model_id="deepseek/deepseek-chat-v3.1",
        input_tokens=2_000,
        output_tokens=1_000,
        latency_ms=800,
    )
    metrics = t.finalize()
    assert metrics.moa_cost_usd > 0
    assert metrics.baseline_cost_usd > 0
    # MoA's editor used 10x more prompt tokens, so its cost must dominate.
    assert metrics.moa_cost_usd > metrics.baseline_cost_usd


def test_tracker_deduplicates_sources() -> None:
    t = RunTracker(mode="brief")
    t.add_sources(["mcp:espn", "mcp:nba_stats", "mcp:espn"])
    metrics = t.finalize()
    assert metrics.distinct_sources == 2
    assert metrics.sources == ["mcp:espn", "mcp:nba_stats"]


def test_tracker_flags_estimated_price_when_any_model_is_estimated() -> None:
    t = RunTracker(mode="brief")
    t.record_llm_call(
        agent="news",
        model_id="this/model/does-not-exist",
        input_tokens=100,
        output_tokens=50,
        latency_ms=200,
    )
    assert t.finalize().estimated_price is True


# ─── ContextVar plumbing ────────────────────────────────────────────────────


def test_use_tracker_binds_and_restores_context() -> None:
    assert current_tracker() is None
    t = RunTracker(mode="brief")
    with use_tracker(t):
        assert current_tracker() is t
    assert current_tracker() is None


# ─── Repository round-trip ──────────────────────────────────────────────────


async def _make_repo(tmp_path: Path) -> EvalRepository:
    repo = EvalRepository(tmp_path / "eval.db")
    await repo.initialize()
    return repo


async def test_repository_round_trip(tmp_path: Path) -> None:
    repo = await _make_repo(tmp_path)
    try:
        t = RunTracker(mode="brief")
        t.record_llm_call(
            agent="editor",
            model_id="deepseek/deepseek-chat-v3.1",
            input_tokens=500,
            output_tokens=200,
            latency_ms=400,
        )
        t.record_tool_call(
            agent="news",
            tool="espn_nba_headlines",
            latency_ms=120,
            success=False,
            error="boom",
        )
        t.add_sources(["mcp:espn"])
        metrics = t.finalize()
        await repo.save_run(
            metrics=metrics,
            date="2025-05-18",
            query="",
            language="en",
            final_brief="brief body",
            single_llm_answer="",
            payload={"hello": "world"},
        )

        runs = await repo.list_runs(limit=10)
        assert len(runs) == 1
        assert runs[0].run_id == metrics.run_id
        assert runs[0].tool_failure_count == 1

        agents = await repo.get_agent_metrics(metrics.run_id)
        assert isinstance(agents[0], AgentMetrics)
        assert any(a.agent == "editor" and a.llm_calls == 1 for a in agents)

        calls = await repo.get_tool_calls(metrics.run_id)
        assert isinstance(calls[0], ToolCallMetric)
        assert calls[0].success is False

        summary = await repo.summary(last_n=10)
        assert summary.total_runs == 1
        assert summary.tool_failure_rate == 1.0
        assert summary.last_run_at is not None
    finally:
        await repo.close()


async def test_repository_filters_by_mode(tmp_path: Path) -> None:
    repo = await _make_repo(tmp_path)
    try:
        for mode in ("brief", "query", "compare", "brief"):
            t = RunTracker(mode=mode)  # type: ignore[arg-type]
            t.record_llm_call(
                agent="x",
                model_id="google/gemini-2.5-flash",
                input_tokens=1,
                output_tokens=1,
                latency_ms=1,
            )
            metrics = t.finalize()
            await repo.save_run(
                metrics=metrics,
                date="2025-05-18",
                query="",
                language="en",
                final_brief="",
                single_llm_answer="",
                payload={},
            )

        all_runs = await repo.list_runs(limit=10)
        assert len(all_runs) == 4

        brief_runs = await repo.list_runs(limit=10, mode="brief")
        assert {r.mode for r in brief_runs} == {"brief"}
        assert len(brief_runs) == 2

        all_summary = await repo.summary(last_n=10)
        assert all_summary.total_runs == 4

        query_summary = await repo.summary(last_n=10, mode="query")
        assert query_summary.total_runs == 1
        assert set(query_summary.cost_by_mode.keys()) == {"query"}
    finally:
        await repo.close()


def test_sources_from_tool_output() -> None:
    from app.moa.agents.base import sources_from_tool_output

    text = '{"items":[{"link":"https://www.espn.com/nba/story"}]}'
    sources = sources_from_tool_output("espn_nba_headlines", text)
    assert "mcp:espn_nba_headlines" in sources
    assert "https://www.espn.com/nba/story" in sources


async def test_repository_summary_handles_empty_db(tmp_path: Path) -> None:
    repo = await _make_repo(tmp_path)
    try:
        summary = await repo.summary(last_n=10)
        assert summary.total_runs == 0
        assert summary.avg_cost_usd == 0.0
        assert summary.last_run_at is None
    finally:
        await repo.close()
