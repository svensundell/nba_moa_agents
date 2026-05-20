"""Postgres repository for indexed Daily Brief memory."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.memory.models import BriefRow, ChunkRow
from app.memory.schemas import BriefSummary


class MemoryRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def initialize(self) -> None:
        """No-op: schema lifecycle is owned by Alembic."""

    async def close(self) -> None:
        """No-op: engine lifecycle is owned by app.db.session."""

    async def has_brief(self, brief_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(BriefRow.brief_id).where(BriefRow.brief_id == brief_id).limit(1)
            )
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
        indexed_at = datetime.now()
        async with self._session_factory() as session, session.begin():
            stmt = insert(BriefRow).values(
                brief_id=brief_id,
                run_id=run_id,
                date=date_value,
                language=language,
                title=title,
                body_markdown=body_markdown,
                indexed_at=indexed_at,
                chunk_count=len(chunks),
            )
            await session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[BriefRow.brief_id],
                    set_={
                        "run_id": run_id,
                        "date": date_value,
                        "language": language,
                        "title": title,
                        "body_markdown": body_markdown,
                        "indexed_at": indexed_at,
                        "chunk_count": len(chunks),
                    },
                )
            )

            await session.execute(delete(ChunkRow).where(ChunkRow.brief_id == brief_id))
            if chunks:
                session.add_all(
                    ChunkRow(
                        brief_id=brief_id,
                        date=date_value,
                        section=section,
                        content=content,
                        embedding=embedding,
                    )
                    for section, content, embedding in chunks
                )
        return len(chunks)

    async def list_briefs(self, *, limit: int = 50) -> list[BriefSummary]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(
                    BriefRow.brief_id,
                    BriefRow.run_id,
                    BriefRow.date,
                    BriefRow.language,
                    BriefRow.title,
                    BriefRow.chunk_count,
                    BriefRow.indexed_at,
                )
                .order_by(desc(BriefRow.date), desc(BriefRow.indexed_at))
                .limit(limit)
            )
            rows = result.all()
        return [
            BriefSummary(
                brief_id=row[0],
                run_id=row[1],
                date=row[2],
                language=row[3],
                title=row[4] or "",
                chunk_count=row[5],
                indexed_at=row[6],
            )
            for row in rows
        ]

    async def fetch_chunks_for_search(
        self,
        *,
        days: int,
        since_date: str | None = None,
        query_embedding: list[float] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        cutoff = since_date or (date.today() - timedelta(days=days)).isoformat()
        async with self._session_factory() as session:
            if query_embedding is not None:
                distance = ChunkRow.embedding.cosine_distance(query_embedding)
                stmt = (
                    select(
                        ChunkRow.chunk_id,
                        ChunkRow.brief_id,
                        ChunkRow.date,
                        ChunkRow.section,
                        ChunkRow.content,
                        ChunkRow.embedding,
                        distance.label("distance"),
                    )
                    .where(ChunkRow.date >= cutoff)
                    .where(ChunkRow.embedding.is_not(None))
                    .order_by(distance)
                )
                if limit is not None:
                    stmt = stmt.limit(limit)
                result = await session.execute(stmt)
                rows = result.all()
                if rows:
                    return [
                        {
                            "chunk_id": str(row[0]),
                            "brief_id": row[1],
                            "date": row[2],
                            "section": row[3],
                            "content": row[4],
                            "embedding": row[5],
                            "score": max(0.0, 1.0 - float(row[6])),
                        }
                        for row in rows
                    ]

            stmt = (
                select(
                    ChunkRow.chunk_id,
                    ChunkRow.brief_id,
                    ChunkRow.date,
                    ChunkRow.section,
                    ChunkRow.content,
                    ChunkRow.embedding,
                )
                .where(ChunkRow.date >= cutoff)
                .order_by(desc(ChunkRow.date))
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            rows = result.all()
            return [
                {
                    "chunk_id": str(row[0]),
                    "brief_id": row[1],
                    "date": row[2],
                    "section": row[3],
                    "content": row[4],
                    "embedding": row[5],
                }
                for row in rows
            ]

    async def chunk_count(self) -> int:
        async with self._session_factory() as session:
            row = await session.scalar(select(func.count()).select_from(ChunkRow))
            return int(row or 0)


_repository: MemoryRepository | None = None


def configure_repository(
    session_factory: async_sessionmaker[AsyncSession],
) -> MemoryRepository:
    global _repository
    _repository = MemoryRepository(session_factory)
    return _repository


def get_repository() -> MemoryRepository:
    if _repository is None:
        raise RuntimeError("Memory repository is not configured.")
    return _repository
