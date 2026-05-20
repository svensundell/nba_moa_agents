"""Async SQLite persistence for indexed Daily Brief memory."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from app.memory.schemas import BriefSummary, MemoryChunkHit

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS briefs (
    brief_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    date TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    title TEXT NOT NULL DEFAULT '',
    body_markdown TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_briefs_date ON briefs (date DESC);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    brief_id TEXT NOT NULL,
    date TEXT NOT NULL,
    section TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    embedding_json TEXT,
    FOREIGN KEY (brief_id) REFERENCES briefs(brief_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_brief_id ON chunks (brief_id);
CREATE INDEX IF NOT EXISTS idx_chunks_date ON chunks (date DESC);
"""


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


class MemoryRepository:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()
        logger.info(f"Memory repository ready at {self.db_path}")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError(
                "MemoryRepository is not initialised — call initialize() first."
            )
        return self._conn

    async def has_brief(self, brief_id: str) -> bool:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT 1 FROM briefs WHERE brief_id = ? LIMIT 1", (brief_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return row is not None

    async def upsert_brief(
        self,
        *,
        brief_id: str,
        run_id: str,
        date_value: str,
        language: str,
        title: str,
        body_markdown: str,
        chunks: list[tuple[str, str, list[float] | None]],
    ) -> int:
        """Replace a brief and its chunks. Returns chunk count."""
        conn = self._require_conn()
        indexed_at = _iso(datetime.now())
        try:
            await conn.execute("DELETE FROM chunks WHERE brief_id = ?", (brief_id,))
            await conn.execute(
                """
                INSERT OR REPLACE INTO briefs (
                    brief_id, run_id, date, language, title,
                    body_markdown, indexed_at, chunk_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    brief_id,
                    run_id,
                    date_value,
                    language,
                    title,
                    body_markdown,
                    indexed_at,
                    len(chunks),
                ),
            )
            for section, content, embedding in chunks:
                emb_json = json.dumps(embedding) if embedding is not None else None
                await conn.execute(
                    """
                    INSERT INTO chunks (
                        chunk_id, brief_id, date, section, content, embedding_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        brief_id,
                        date_value,
                        section,
                        content,
                        emb_json,
                    ),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        return len(chunks)

    async def list_briefs(self, *, limit: int = 50) -> list[BriefSummary]:
        conn = self._require_conn()
        async with conn.execute(
            """
            SELECT brief_id, run_id, date, language, title, chunk_count, indexed_at
            FROM briefs
            ORDER BY date DESC, indexed_at DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            BriefSummary(
                brief_id=row[0],
                run_id=row[1],
                date=row[2],
                language=row[3],
                title=row[4] or "",
                chunk_count=row[5],
                indexed_at=_parse_iso(row[6]),
            )
            for row in rows
        ]

    async def fetch_chunks_for_search(
        self,
        *,
        days: int,
        since_date: str | None = None,
    ) -> list[dict[str, Any]]:
        conn = self._require_conn()
        if since_date:
            cutoff = since_date
        else:
            cutoff = (date.today() - timedelta(days=days)).isoformat()
        async with conn.execute(
            """
            SELECT chunk_id, brief_id, date, section, content, embedding_json
            FROM chunks
            WHERE date >= ?
            ORDER BY date DESC
            """,
            (cutoff,),
        ) as cursor:
            rows = await cursor.fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            emb: list[float] | None = None
            if row[5]:
                try:
                    emb = json.loads(row[5])
                except json.JSONDecodeError:
                    emb = None
            out.append(
                {
                    "chunk_id": row[0],
                    "brief_id": row[1],
                    "date": row[2],
                    "section": row[3],
                    "content": row[4],
                    "embedding": emb,
                }
            )
        return out

    async def chunk_count(self) -> int:
        conn = self._require_conn()
        async with conn.execute("SELECT COUNT(*) FROM chunks") as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0


_repository: MemoryRepository | None = None


def configure_repository(db_path: Path | str) -> MemoryRepository:
    global _repository
    _repository = MemoryRepository(db_path)
    return _repository


def get_repository() -> MemoryRepository:
    if _repository is None:
        raise RuntimeError("Memory repository is not configured.")
    return _repository
