"""Async SQLite persistence for evaluation runs.

We keep three tables on purpose:

* ``runs`` — one row per pipeline invocation, with the JSON-serialised
  final payload so the detail page can render the brief without
  consulting any other store.
* ``agent_metrics`` — denormalised per-agent rows. Lets the dashboard
  group by ``agent`` or ``model`` across the whole history without
  parsing JSON in every query.
* ``tool_calls`` — one row per MCP call. Powers the tool failure
  breakdown and per-tool latency charts.

SQLite was chosen over Postgres because the project still runs locally
and the file ships in ``data/eval.db``. The schema is plain enough that
swapping in any SQLAlchemy backend later is a one-day job.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from app.eval.schemas import (
    AgentMetrics,
    DashboardSummary,
    RunMetrics,
    RunSummary,
    ToolCallMetric,
)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    date TEXT NOT NULL,
    query TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'en',
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    total_input_tokens INTEGER NOT NULL DEFAULT 0,
    total_output_tokens INTEGER NOT NULL DEFAULT 0,
    total_cost_usd REAL NOT NULL DEFAULT 0,
    llm_call_count INTEGER NOT NULL DEFAULT 0,
    tool_call_count INTEGER NOT NULL DEFAULT 0,
    tool_failure_count INTEGER NOT NULL DEFAULT 0,
    distinct_sources INTEGER NOT NULL DEFAULT 0,
    moa_cost_usd REAL NOT NULL DEFAULT 0,
    baseline_cost_usd REAL NOT NULL DEFAULT 0,
    estimated_price INTEGER NOT NULL DEFAULT 0,
    final_brief TEXT NOT NULL DEFAULT '',
    single_llm_answer TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_mode ON runs (mode);

CREATE TABLE IF NOT EXISTS agent_metrics (
    run_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    llm_calls INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    llm_latency_ms REAL NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    tool_failures INTEGER NOT NULL DEFAULT 0,
    tool_latency_ms REAL NOT NULL DEFAULT 0,
    wall_clock_ms REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, agent),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tool_calls (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    agent TEXT NOT NULL,
    tool TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    success INTEGER NOT NULL,
    error TEXT,
    started_at TEXT NOT NULL,
    PRIMARY KEY (run_id, seq),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_tool ON tool_calls (tool);
"""


def _iso(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class EvalRepository:
    """Thin async wrapper around an aiosqlite connection.

    The connection is opened lazily on first use and reused across
    requests. ``aiosqlite`` serialises writes per-connection, which is
    exactly what we want for a single-file SQLite database.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open the connection and run the schema migration."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()
        logger.info(f"Eval repository ready at {self.db_path}")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError(
                "EvalRepository is not initialised — call initialize() first."
            )
        return self._conn

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

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
        """Insert a full run + its agent / tool rows in one transaction.

        aiosqlite inherits sqlite3's deferred isolation level, so the
        first ``execute`` opens an implicit transaction. We commit at the
        end (or rollback on error).
        """
        conn = self._require_conn()
        try:
            await conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, mode, date, query, language,
                    started_at, finished_at, duration_seconds,
                    total_input_tokens, total_output_tokens, total_cost_usd,
                    llm_call_count, tool_call_count, tool_failure_count,
                    distinct_sources, moa_cost_usd, baseline_cost_usd,
                    estimated_price, final_brief, single_llm_answer, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metrics.run_id,
                    metrics.mode,
                    date,
                    query,
                    language,
                    _iso(metrics.started_at),
                    _iso(metrics.finished_at),
                    metrics.duration_seconds,
                    metrics.total_input_tokens,
                    metrics.total_output_tokens,
                    metrics.total_cost_usd,
                    metrics.llm_call_count,
                    metrics.tool_call_count,
                    metrics.tool_failure_count,
                    metrics.distinct_sources,
                    metrics.moa_cost_usd,
                    metrics.baseline_cost_usd,
                    1 if metrics.estimated_price else 0,
                    final_brief,
                    single_llm_answer,
                    json.dumps(payload, default=str),
                ),
            )

            await conn.execute(
                "DELETE FROM agent_metrics WHERE run_id = ?", (metrics.run_id,)
            )
            if metrics.agents:
                await conn.executemany(
                    """
                    INSERT INTO agent_metrics (
                        run_id, agent, model, llm_calls,
                        input_tokens, output_tokens, cost_usd, llm_latency_ms,
                        tool_calls, tool_failures, tool_latency_ms, wall_clock_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            metrics.run_id,
                            a.agent,
                            a.model,
                            a.llm_calls,
                            a.input_tokens,
                            a.output_tokens,
                            a.cost_usd,
                            a.llm_latency_ms,
                            a.tool_calls,
                            a.tool_failures,
                            a.tool_latency_ms,
                            a.wall_clock_ms,
                        )
                        for a in metrics.agents
                    ],
                )

            await conn.execute(
                "DELETE FROM tool_calls WHERE run_id = ?", (metrics.run_id,)
            )
            if metrics.tool_calls:
                await conn.executemany(
                    """
                    INSERT INTO tool_calls (
                        run_id, seq, agent, tool, latency_ms,
                        success, error, started_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            metrics.run_id,
                            i,
                            t.agent,
                            t.tool,
                            t.latency_ms,
                            1 if t.success else 0,
                            t.error,
                            _iso(t.started_at),
                        )
                        for i, t in enumerate(metrics.tool_calls)
                    ],
                )

            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def list_runs(
        self,
        *,
        limit: int = 50,
        mode: str | None = None,
    ) -> list[RunSummary]:
        conn = self._require_conn()
        sql = (
            "SELECT run_id, mode, date, query, language, started_at, duration_seconds, "
            "total_cost_usd, total_input_tokens, total_output_tokens, llm_call_count, "
            "tool_call_count, tool_failure_count, distinct_sources, moa_cost_usd, "
            "baseline_cost_usd, estimated_price "
            "FROM runs"
        )
        params: tuple[Any, ...]
        if mode:
            sql += " WHERE mode = ? ORDER BY started_at DESC LIMIT ?"
            params = (mode, limit)
        else:
            sql += " ORDER BY started_at DESC LIMIT ?"
            params = (limit,)

        async with conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()

        return [
            RunSummary(
                run_id=row[0],
                mode=row[1],
                date=row[2],
                query=row[3] or "",
                language=row[4] or "en",
                started_at=_parse_iso(row[5]),
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
        """Return the JSON-serialised RunResult stored for ``run_id``."""
        conn = self._require_conn()
        async with conn.execute(
            "SELECT payload_json FROM runs WHERE run_id = ?", (run_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except (TypeError, ValueError):
            logger.warning(f"Run {run_id} has malformed payload_json")
            return None

    async def get_agent_metrics(self, run_id: str) -> list[AgentMetrics]:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT agent, model, llm_calls, input_tokens, output_tokens, "
            "cost_usd, llm_latency_ms, tool_calls, tool_failures, "
            "tool_latency_ms, wall_clock_ms "
            "FROM agent_metrics WHERE run_id = ? ORDER BY agent",
            (run_id,),
        ) as cursor:
            rows = await cursor.fetchall()
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
        conn = self._require_conn()
        async with conn.execute(
            "SELECT agent, tool, latency_ms, success, error, started_at "
            "FROM tool_calls WHERE run_id = ? ORDER BY seq",
            (run_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            ToolCallMetric(
                agent=row[0],
                tool=row[1],
                latency_ms=row[2],
                success=bool(row[3]),
                error=row[4],
                started_at=_parse_iso(row[5]),
            )
            for row in rows
        ]

    async def summary(self, *, last_n: int = 100) -> DashboardSummary:
        """Aggregate dashboard stats over the last ``last_n`` runs."""
        conn = self._require_conn()

        async with conn.execute(
            "SELECT mode, duration_seconds, total_cost_usd, tool_call_count, "
            "tool_failure_count, moa_cost_usd, baseline_cost_usd, started_at "
            "FROM runs ORDER BY started_at DESC LIMIT ?",
            (last_n,),
        ) as cursor:
            rows = await cursor.fetchall()

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
        for mode, _dur, cost, _tc, _tf, _moa, _baseline, _start in rows:
            cost_by_mode[mode] = cost_by_mode.get(mode, 0.0) + cost
            runs_by_mode[mode] = runs_by_mode.get(mode, 0) + 1
        avg_cost_by_mode = {
            mode: cost_by_mode[mode] / runs_by_mode[mode] for mode in cost_by_mode
        }

        compare_rows = [r for r in rows if r[0] == "compare"]
        compare_avg_moa = (
            sum(r[5] for r in compare_rows) / len(compare_rows)
            if compare_rows
            else 0.0
        )
        compare_avg_baseline = (
            sum(r[6] for r in compare_rows) / len(compare_rows)
            if compare_rows
            else 0.0
        )

        durations = sorted(r[1] for r in rows)
        p95_idx = max(0, round(0.95 * (len(durations) - 1)))
        p95_duration = durations[p95_idx]

        last_run_at = _parse_iso(rows[0][7])

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


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_repository: EvalRepository | None = None


def configure_repository(db_path: Path | str) -> EvalRepository:
    """Construct (but don't open) the shared :class:`EvalRepository`."""
    global _repository
    _repository = EvalRepository(db_path)
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
