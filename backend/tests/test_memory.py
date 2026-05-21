"""Tests for Daily Brief memory (chunking, repository, search)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.memory.chunking import chunk_brief_markdown, extract_brief_title
from app.memory.embeddings import cosine_similarity, keyword_score
from app.memory.repository import MemoryRepository
from app.memory.service import MemoryService

# Must match default MEMORY_EMBEDDING_DIM / pgvector column size in models.
_TEST_EMBED_DIM = 1536


def _unit_vector(index: int) -> list[float]:
    vec = [0.0] * _TEST_EMBED_DIM
    vec[index % _TEST_EMBED_DIM] = 1.0
    return vec


SAMPLE_BRIEF = """# Last Night in the NBA — 2026-05-18

## Quick Hits
- Pacers force Game 7 with a late run.

## Storyline of the Night
Indiana's pace and switching bothered the favorite all evening.
"""


@pytest.mark.parametrize(
    ("query", "content", "expected_min"),
    [
        ("Pacers storyline", "everyone talks about the Pacers this week", 0.3),
        ("xyz", "unrelated content only", 0.0),
    ],
)
def test_keyword_score(query: str, content: str, expected_min: float) -> None:
    score = keyword_score(query, content)
    assert score >= expected_min


def test_cosine_similarity_identical() -> None:
    v = [1.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_chunk_brief_markdown_sections() -> None:
    chunks = chunk_brief_markdown(SAMPLE_BRIEF)
    sections = {c.section for c in chunks}
    assert "Quick Hits" in sections
    assert "Storyline of the Night" in sections
    assert all(c.content.strip() for c in chunks)


def test_extract_brief_title() -> None:
    assert extract_brief_title(SAMPLE_BRIEF).startswith("Last Night in the NBA")


@pytest.mark.asyncio
async def test_memory_repository_and_search(pg_session_factory) -> None:
    repo = MemoryRepository(pg_session_factory)
    await repo.initialize()
    service = MemoryService(repo)

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        return [_unit_vector(i) for i in range(len(texts))]

    settings = patch("app.memory.service.get_settings")
    with (
        settings as gs,
        patch(
            "app.memory.service.embed_texts",
            new=AsyncMock(side_effect=fake_embed),
        ),
    ):
        gs.return_value.memory_enabled = True
        gs.return_value.memory_default_days = 30
        gs.return_value.memory_search_top_k = 6
        n = await service.index_brief(
            brief_id="run-1",
            run_id="run-1",
            date_value="2026-05-18",
            language="en",
            markdown=SAMPLE_BRIEF,
            force=True,
        )
        assert n >= 2

        result = await service.search("Pacers Game 7", days=30, limit=3)

    assert result.hits
    assert result.hits[0].content
    await repo.close()


@pytest.mark.asyncio
async def test_memory_skips_duplicate_index(pg_session_factory) -> None:
    repo = MemoryRepository(pg_session_factory)
    await repo.initialize()
    service = MemoryService(repo)

    settings = patch("app.memory.service.get_settings")

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        vec = [0.0] * _TEST_EMBED_DIM
        vec[0] = 0.5
        vec[1] = 0.5
        return [vec.copy() for _ in texts]

    with (
        settings as gs,
        patch(
            "app.memory.service.embed_texts",
            new=AsyncMock(side_effect=fake_embed),
        ),
    ):
        gs.return_value.memory_enabled = True
        first = await service.index_brief(
            brief_id="run-dup",
            run_id="run-dup",
            date_value="2026-05-17",
            language="en",
            markdown=SAMPLE_BRIEF,
        )
        second = await service.index_brief(
            brief_id="run-dup",
            run_id="run-dup",
            date_value="2026-05-17",
            language="en",
            markdown=SAMPLE_BRIEF,
        )
    assert first > 0
    assert second == 0
    await repo.close()
