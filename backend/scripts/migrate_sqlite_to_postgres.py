"""One-off migration from legacy SQLite stores to Postgres.

Usage:
  python -m scripts.migrate_sqlite_to_postgres

Environment:
  DATABASE_URL     target Postgres DSN (asyncpg)
  EVAL_DB_PATH     optional legacy eval sqlite path
  MEMORY_DB_PATH   optional legacy memory sqlite path
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from loguru import logger

from app.core.config import get_settings
from app.db import close_engine, configure_engine, get_session_factory
from app.eval.repository import EvalRepository
from app.eval.schemas import AgentMetrics, RunMetrics, ToolCallMetric
from app.memory.repository import MemoryRepository


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _load_eval_rows(path: Path) -> list[dict]:
    if not path.exists():
        logger.warning(f"Legacy eval sqlite not found: {path}")
        return []

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        runs = conn.execute("SELECT * FROM runs ORDER BY started_at ASC").fetchall()
        out: list[dict] = []
        for run in runs:
            run_id = run["run_id"]
            agents = conn.execute(
                "SELECT * FROM agent_metrics WHERE run_id = ? ORDER BY agent", (run_id,)
            ).fetchall()
            tools = conn.execute(
                "SELECT * FROM tool_calls WHERE run_id = ? ORDER BY seq", (run_id,)
            ).fetchall()
            out.append(
                {
                    "run": dict(run),
                    "agents": [dict(a) for a in agents],
                    "tools": [dict(t) for t in tools],
                }
            )
        return out
    finally:
        conn.close()


def _load_memory_rows(path: Path) -> list[dict]:
    if not path.exists():
        logger.warning(f"Legacy memory sqlite not found: {path}")
        return []

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        briefs = conn.execute("SELECT * FROM briefs ORDER BY indexed_at ASC").fetchall()
        out: list[dict] = []
        for brief in briefs:
            brief_id = brief["brief_id"]
            chunks = conn.execute(
                "SELECT section, content, embedding_json FROM chunks WHERE brief_id = ?",
                (brief_id,),
            ).fetchall()
            out.append(
                {
                    "brief": dict(brief),
                    "chunks": [dict(c) for c in chunks],
                }
            )
        return out
    finally:
        conn.close()


async def migrate_eval(repo: EvalRepository, eval_path: Path) -> int:
    rows = _load_eval_rows(eval_path)
    migrated = 0
    for item in rows:
        run = item["run"]
        metrics = RunMetrics(
            run_id=run["run_id"],
            mode=run["mode"],
            started_at=_parse_iso(run["started_at"]),
            finished_at=_parse_iso(run["finished_at"]),
            duration_seconds=float(run["duration_seconds"]),
            total_input_tokens=int(run["total_input_tokens"]),
            total_output_tokens=int(run["total_output_tokens"]),
            total_cost_usd=float(run["total_cost_usd"]),
            llm_call_count=int(run["llm_call_count"]),
            tool_call_count=int(run["tool_call_count"]),
            tool_failure_count=int(run["tool_failure_count"]),
            distinct_sources=int(run["distinct_sources"]),
            moa_cost_usd=float(run["moa_cost_usd"]),
            baseline_cost_usd=float(run["baseline_cost_usd"]),
            estimated_price=bool(run["estimated_price"]),
            agents=[
                AgentMetrics(
                    agent=a["agent"],
                    model=a["model"],
                    llm_calls=int(a["llm_calls"]),
                    input_tokens=int(a["input_tokens"]),
                    output_tokens=int(a["output_tokens"]),
                    cost_usd=float(a["cost_usd"]),
                    llm_latency_ms=float(a["llm_latency_ms"]),
                    tool_calls=int(a["tool_calls"]),
                    tool_failures=int(a["tool_failures"]),
                    tool_latency_ms=float(a["tool_latency_ms"]),
                    wall_clock_ms=float(a["wall_clock_ms"]),
                )
                for a in item["agents"]
            ],
            tool_calls=[
                ToolCallMetric(
                    agent=t["agent"],
                    tool=t["tool"],
                    latency_ms=float(t["latency_ms"]),
                    success=bool(t["success"]),
                    error=t["error"],
                    started_at=_parse_iso(t["started_at"]),
                )
                for t in item["tools"]
            ],
            sources=[],
        )

        payload_raw = run.get("payload_json") or "{}"
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {}

        await repo.save_run(
            metrics=metrics,
            date=run["date"],
            query=run["query"] or "",
            language=run["language"] or "en",
            final_brief=run["final_brief"] or "",
            single_llm_answer=run["single_llm_answer"] or "",
            payload=payload,
        )
        migrated += 1
    return migrated


async def migrate_memory(repo: MemoryRepository, memory_path: Path) -> int:
    rows = _load_memory_rows(memory_path)
    migrated = 0
    for item in rows:
        brief = item["brief"]
        chunks: list[tuple[str, str, list[float] | None]] = []
        for row in item["chunks"]:
            embedding = None
            if row.get("embedding_json"):
                try:
                    embedding = json.loads(row["embedding_json"])
                except json.JSONDecodeError:
                    embedding = None
            chunks.append((row["section"] or "", row["content"] or "", embedding))

        await repo.upsert_brief(
            brief_id=brief["brief_id"],
            run_id=brief["run_id"],
            date_value=brief["date"],
            language=brief["language"] or "en",
            title=brief["title"] or "",
            body_markdown=brief["body_markdown"] or "",
            chunks=chunks,
        )
        migrated += 1
    return migrated


async def amain() -> None:
    settings = get_settings()
    configure_engine(settings.database_url, echo=settings.db_echo)
    session_factory = get_session_factory()

    eval_repo = EvalRepository(session_factory)
    memory_repo = MemoryRepository(session_factory)

    eval_count = await migrate_eval(eval_repo, settings.resolved_legacy_eval_db_path)
    memory_count = await migrate_memory(
        memory_repo, settings.resolved_legacy_memory_db_path
    )

    logger.info(f"Migrated runs: {eval_count}")
    logger.info(f"Migrated briefs: {memory_count}")
    await close_engine()


if __name__ == "__main__":
    asyncio.run(amain())
