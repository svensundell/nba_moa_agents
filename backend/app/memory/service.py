"""Index Daily Briefs and search them for NBA Copilot context."""

from __future__ import annotations

from loguru import logger

from app.core.config import get_settings
from app.memory.chunking import chunk_brief_markdown, extract_brief_title
from app.memory.embeddings import cosine_similarity, embed_texts, keyword_score
from app.memory.repository import MemoryRepository
from app.memory.schemas import BriefSummary, MemoryChunkHit, MemorySearchResult

_service: MemoryService | None = None


class MemoryService:
    def __init__(self, repo: MemoryRepository) -> None:
        self._repo = repo

    async def initialize(self) -> None:
        await self._repo.initialize()

    async def close(self) -> None:
        await self._repo.close()

    @property
    def enabled(self) -> bool:
        settings = get_settings()
        return settings.memory_enabled

    async def index_brief(
        self,
        *,
        brief_id: str,
        run_id: str,
        date_value: str,
        language: str,
        markdown: str,
        force: bool = False,
    ) -> int:
        """Chunk, embed, and store a Daily Brief. Returns number of chunks."""
        if not self.enabled:
            logger.debug("Brief memory indexing skipped (disabled or no API key).")
            return 0

        body = markdown.strip()
        if not body:
            return 0

        if not force and await self._repo.has_brief(brief_id):
            logger.debug(f"Brief {brief_id} already indexed — skipping.")
            return 0

        drafts = chunk_brief_markdown(body)
        if not drafts:
            return 0

        texts = [d.content for d in drafts]
        embeddings: list[list[float] | None]
        try:
            vectors = await embed_texts(texts)
            embeddings = [v for v in vectors]
        except Exception as exc:
            logger.warning(f"Embedding failed for brief {brief_id}: {exc} — keyword fallback only.")
            embeddings = [None] * len(texts)

        rows = [(draft.section, draft.content, embeddings[i]) for i, draft in enumerate(drafts)]
        title = extract_brief_title(body)
        count = await self._repo.upsert_brief(
            brief_id=brief_id,
            run_id=run_id,
            date_value=date_value,
            language=language,
            title=title,
            body_markdown=body,
            chunks=rows,
        )
        logger.info(f"Indexed brief {brief_id} ({date_value}): {count} chunks.")
        return count

    async def search(
        self,
        query: str,
        *,
        days: int | None = None,
        since_date: str | None = None,
        limit: int | None = None,
    ) -> MemorySearchResult:
        settings = get_settings()
        window = days if days is not None else settings.memory_default_days
        top_k = limit if limit is not None else settings.memory_search_top_k

        query_vec: list[float] | None = None
        if self.enabled:
            try:
                query_vec = (await embed_texts([query.strip()]))[0]
            except Exception as exc:
                logger.warning(f"Query embedding failed: {exc}")

        chunks = await self._repo.fetch_chunks_for_search(
            days=window,
            since_date=since_date,
            query_embedding=query_vec,
            limit=top_k * 6 if query_vec is not None else None,
        )
        if not chunks:
            return MemorySearchResult(query=query, days=window, hits=[])

        scored: list[tuple[float, dict]] = []
        for row in chunks:
            existing_score = row.get("score")
            if isinstance(existing_score, (float, int)):
                score = float(existing_score)
                if score > 0:
                    scored.append((score, row))
                continue
            emb = row.get("embedding")
            if query_vec is not None and isinstance(emb, list) and emb:
                score = cosine_similarity(query_vec, emb)
            else:
                score = keyword_score(query, row["content"])
            if score > 0:
                scored.append((score, row))

        scored.sort(key=lambda item: item[0], reverse=True)
        hits = [
            MemoryChunkHit(
                chunk_id=row["chunk_id"],
                brief_id=row["brief_id"],
                date=row["date"],
                section=row["section"],
                content=row["content"],
                score=round(score, 4),
            )
            for score, row in scored[:top_k]
        ]
        return MemorySearchResult(query=query, days=window, hits=hits)

    async def list_briefs(self, *, limit: int = 50) -> list[BriefSummary]:
        return await self._repo.list_briefs(limit=limit)

    def format_hits_for_tool(self, result: MemorySearchResult) -> str:
        if not result.hits:
            return (
                f"No matching Daily Brief excerpts found in the last {result.days} days. "
                "Use live MCP tools for current data."
            )
        lines = [
            f"Past Daily Brief excerpts (last {result.days} days, ranked by relevance):",
            "",
        ]
        for i, hit in enumerate(result.hits, start=1):
            preview = hit.content.strip()
            if len(preview) > 900:
                preview = preview[:900] + "…"
            lines.append(
                f"[memory-{i}] {hit.date} — {hit.section} (brief {hit.brief_id[:8]}…)\n{preview}"
            )
            lines.append("")
        lines.append(
            "Treat these as historical context. Prefer live MCP tools for scores, "
            "injuries, and breaking news."
        )
        return "\n".join(lines)


def configure_memory(repo: MemoryRepository) -> MemoryService:
    global _service
    _service = MemoryService(repo)
    return _service


def get_memory_service() -> MemoryService:
    if _service is None:
        raise RuntimeError("Memory service is not configured.")
    return _service
