"""Postgres persistence for evaluation runs using SQLAlchemy async."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, desc, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.eval.models import AgentMetricRow, RunRow, ToolCallRow
from app.eval.schemas import (
    AgentMetrics,
    DashboardSummary,
    RunMetrics,
    RunSummary,
    ToolCallMetric,
)


class EvalRepository:
    """Thin async wrapper around SQLAlchemy persistence methods."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def initialize(self) -> None:
        """No-op: schema lifecycle is owned by Alembic."""

    async def close(self) -> None:
        """No-op: engine lifecycle is owned by app.db.session."""

    async def save_run(
        self,
        *,
        metrics: RunMetrics,
        date: str,
        query: str,
        language: str,
        final_brief: str,
        single_llm_answer: str,
        payload: dict[str, Any],
    ) -> None:
        async with self._session_factory() as session, session.begin():
            stmt = insert(RunRow).values(
                run_id=metrics.run_id,
                mode=metrics.mode,
                date=date,
                query=query,
                language=language,
                started_at=metrics.started_at,
                finished_at=metrics.finished_at,
                duration_seconds=metrics.duration_seconds,
                total_input_tokens=metrics.total_input_tokens,
                total_output_tokens=metrics.total_output_tokens,
                total_cost_usd=metrics.total_cost_usd,
                llm_call_count=metrics.llm_call_count,
                tool_call_count=metrics.tool_call_count,
                tool_failure_count=metrics.tool_failure_count,
                distinct_sources=metrics.distinct_sources,
                moa_cost_usd=metrics.moa_cost_usd,
                baseline_cost_usd=metrics.baseline_cost_usd,
                estimated_price=metrics.estimated_price,
                final_brief=final_brief,
                single_llm_answer=single_llm_answer,
                payload_json=json.dumps(payload, default=str),
            )
            await session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[RunRow.run_id],
                    set_={
                        "mode": metrics.mode,
                        "date": date,
                        "query": query,
                        "language": language,
                        "started_at": metrics.started_at,
                        "finished_at": metrics.finished_at,
                        "duration_seconds": metrics.duration_seconds,
                        "total_input_tokens": metrics.total_input_tokens,
                        "total_output_tokens": metrics.total_output_tokens,
                        "total_cost_usd": metrics.total_cost_usd,
                        "llm_call_count": metrics.llm_call_count,
                        "tool_call_count": metrics.tool_call_count,
                        "tool_failure_count": metrics.tool_failure_count,
                        "distinct_sources": metrics.distinct_sources,
                        "moa_cost_usd": metrics.moa_cost_usd,
                        "baseline_cost_usd": metrics.baseline_cost_usd,
                        "estimated_price": metrics.estimated_price,
                        "final_brief": final_brief,
                        "single_llm_answer": single_llm_answer,
                        "payload_json": json.dumps(payload, default=str),
                    },
                )
            )

            await session.execute(
                delete(AgentMetricRow).where(AgentMetricRow.run_id == metrics.run_id)
            )
            if metrics.agents:
                session.add_all(
                    AgentMetricRow(
                        run_id=metrics.run_id,
                        agent=a.agent,
                        model=a.model,
                        llm_calls=a.llm_calls,
                        input_tokens=a.input_tokens,
                        output_tokens=a.output_tokens,
                        cost_usd=a.cost_usd,
                        llm_latency_ms=a.llm_latency_ms,
                        tool_calls=a.tool_calls,
                        tool_failures=a.tool_failures,
                        tool_latency_ms=a.tool_latency_ms,
                        wall_clock_ms=a.wall_clock_ms,
                    )
                    for a in metrics.agents
                )

            await session.execute(delete(ToolCallRow).where(ToolCallRow.run_id == metrics.run_id))
            if metrics.tool_calls:
                session.add_all(
                    ToolCallRow(
                        run_id=metrics.run_id,
                        seq=i,
                        agent=t.agent,
                        tool=t.tool,
                        latency_ms=t.latency_ms,
                        success=t.success,
                        error=t.error,
                        started_at=t.started_at,
                    )
                    for i, t in enumerate(metrics.tool_calls)
                )

    async def list_runs(
        self,
        *,
        limit: int = 50,
        mode: str | None = None,
    ) -> list[RunSummary]:
        async with self._session_factory() as session:
            stmt = select(
                RunRow.run_id,
                RunRow.mode,
                RunRow.date,
                RunRow.query,
                RunRow.language,
                RunRow.started_at,
                RunRow.duration_seconds,
                RunRow.total_cost_usd,
                RunRow.total_input_tokens,
                RunRow.total_output_tokens,
                RunRow.llm_call_count,
                RunRow.tool_call_count,
                RunRow.tool_failure_count,
                RunRow.distinct_sources,
                RunRow.moa_cost_usd,
                RunRow.baseline_cost_usd,
                RunRow.estimated_price,
            )
            if mode:
                stmt = stmt.where(RunRow.mode == mode)
            stmt = stmt.order_by(desc(RunRow.started_at)).limit(limit)
            rows = (await session.execute(stmt)).all()

        return [
            RunSummary(
                run_id=row[0],
                mode=row[1],
                date=row[2],
                query=row[3] or "",
                language=row[4] or "en",
                started_at=row[5],
                duration_seconds=row[6],
                total_cost_usd=row[7],
                total_input_tokens=row[8],
                total_output_tokens=row[9],
                llm_call_count=row[10],
                tool_call_count=row[11],
                tool_failure_count=row[12],
                distinct_sources=row[13],
                moa_cost_usd=row[14],
                baseline_cost_usd=row[15],
                estimated_price=bool(row[16]),
            )
            for row in rows
        ]

    async def get_run_payload(self, run_id: str) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            payload = await session.scalar(
                select(RunRow.payload_json).where(RunRow.run_id == run_id)
            )
        if payload is None:
            return None
        try:
            return json.loads(payload)
        except (TypeError, ValueError):
            return None

    async def get_agent_metrics(self, run_id: str) -> list[AgentMetrics]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        AgentMetricRow.agent,
                        AgentMetricRow.model,
                        AgentMetricRow.llm_calls,
                        AgentMetricRow.input_tokens,
                        AgentMetricRow.output_tokens,
                        AgentMetricRow.cost_usd,
                        AgentMetricRow.llm_latency_ms,
                        AgentMetricRow.tool_calls,
                        AgentMetricRow.tool_failures,
                        AgentMetricRow.tool_latency_ms,
                        AgentMetricRow.wall_clock_ms,
                    )
                    .where(AgentMetricRow.run_id == run_id)
                    .order_by(AgentMetricRow.agent)
                )
            ).all()
        return [
            AgentMetrics(
                agent=row[0],
                model=row[1],
                llm_calls=row[2],
                input_tokens=row[3],
                output_tokens=row[4],
                cost_usd=row[5],
                llm_latency_ms=row[6],
                tool_calls=row[7],
                tool_failures=row[8],
                tool_latency_ms=row[9],
                wall_clock_ms=row[10],
            )
            for row in rows
        ]

    async def get_tool_calls(self, run_id: str) -> list[ToolCallMetric]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        ToolCallRow.agent,
                        ToolCallRow.tool,
                        ToolCallRow.latency_ms,
                        ToolCallRow.success,
                        ToolCallRow.error,
                        ToolCallRow.started_at,
                    )
                    .where(ToolCallRow.run_id == run_id)
                    .order_by(ToolCallRow.seq)
                )
            ).all()
        return [
            ToolCallMetric(
                agent=row[0],
                tool=row[1],
                latency_ms=row[2],
                success=bool(row[3]),
                error=row[4],
                started_at=row[5],
            )
            for row in rows
        ]

    async def summary(
        self,
        *,
        last_n: int = 100,
        mode: str | None = None,
    ) -> DashboardSummary:
        async with self._session_factory() as session:
            stmt = select(
                RunRow.mode,
                RunRow.duration_seconds,
                RunRow.total_cost_usd,
                RunRow.tool_call_count,
                RunRow.tool_failure_count,
                RunRow.moa_cost_usd,
                RunRow.baseline_cost_usd,
                RunRow.started_at,
            )
            if mode:
                stmt = stmt.where(RunRow.mode == mode)
            rows = (await session.execute(stmt.order_by(desc(RunRow.started_at)).limit(last_n))).all()

        total_runs = len(rows)
        if total_runs == 0:
            return DashboardSummary(
                total_runs=0,
                avg_cost_usd=0.0,
                avg_duration_seconds=0.0,
                tool_failure_rate=0.0,
                cost_by_mode={},
                avg_cost_by_mode={},
                runs_by_mode={},
                compare_avg_moa_cost_usd=0.0,
                compare_avg_baseline_cost_usd=0.0,
                p95_duration_seconds=0.0,
                last_run_at=None,
            )

        total_cost = sum(r[2] for r in rows)
        total_duration = sum(r[1] for r in rows)
        total_tool_calls = sum(r[3] for r in rows)
        total_tool_failures = sum(r[4] for r in rows)

        cost_by_mode: dict[str, float] = {}
        runs_by_mode: dict[str, int] = {}
        for mode_name, _dur, cost, _tc, _tf, _moa, _baseline, _start in rows:
            cost_by_mode[mode_name] = cost_by_mode.get(mode_name, 0.0) + cost
            runs_by_mode[mode_name] = runs_by_mode.get(mode_name, 0) + 1
        avg_cost_by_mode = {
            mode_name: cost_by_mode[mode_name] / runs_by_mode[mode_name]
            for mode_name in cost_by_mode
        }

        compare_rows = [r for r in rows if r[0] == "compare"]
        compare_avg_moa = (
            sum(r[5] for r in compare_rows) / len(compare_rows) if compare_rows else 0.0
        )
        compare_avg_baseline = (
            sum(r[6] for r in compare_rows) / len(compare_rows) if compare_rows else 0.0
        )

        durations = sorted(r[1] for r in rows)
        p95_idx = max(0, round(0.95 * (len(durations) - 1)))
        p95_duration = durations[p95_idx]

        last_run_at = rows[0][7]

        return DashboardSummary(
            total_runs=total_runs,
            avg_cost_usd=total_cost / total_runs,
            avg_duration_seconds=total_duration / total_runs,
            tool_failure_rate=(
                total_tool_failures / total_tool_calls if total_tool_calls else 0.0
            ),
            cost_by_mode=cost_by_mode,
            avg_cost_by_mode=avg_cost_by_mode,
            runs_by_mode=runs_by_mode,
            compare_avg_moa_cost_usd=compare_avg_moa,
            compare_avg_baseline_cost_usd=compare_avg_baseline,
            p95_duration_seconds=p95_duration,
            last_run_at=last_run_at,
        )


_repository: EvalRepository | None = None


def configure_repository(
    session_factory: async_sessionmaker[AsyncSession],
) -> EvalRepository:
    """Construct the shared :class:`EvalRepository`."""
    global _repository
    _repository = EvalRepository(session_factory)
    return _repository


def get_repository() -> EvalRepository:
    """Return the configured repository, raising if none is set."""
    if _repository is None:
        raise RuntimeError(
            "Eval repository is not configured. Call configure_repository() first."
        )
    return _repository


__all__ = [
    "EvalRepository",
    "configure_repository",
    "get_repository",
]
