"""OpenRouter-backed text embeddings for brief memory retrieval."""

from __future__ import annotations

import math
from functools import lru_cache

import httpx

from app.core.config import get_settings

DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"


@lru_cache
def embedding_model_id() -> str:
    settings = get_settings()
    return settings.memory_embedding_model or DEFAULT_EMBEDDING_MODEL


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings via OpenRouter's OpenAI-compatible API."""
    if not texts:
        return []
    settings = get_settings()
    if not settings.has_openrouter:
        raise RuntimeError("OPENROUTER_API_KEY is required for brief memory embeddings.")

    url = f"{settings.openrouter_base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": embedding_model_id(), "input": texts}

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    rows = data.get("data") or []
    if len(rows) != len(texts):
        raise RuntimeError(
            f"Embedding API returned {len(rows)} vectors for {len(texts)} inputs."
        )
    ordered = sorted(rows, key=lambda row: row.get("index", 0))
    return [list(row["embedding"]) for row in ordered]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def keyword_score(query: str, content: str) -> float:
    """Cheap fallback when embeddings are unavailable."""
    q_tokens = {t.lower() for t in query.split() if len(t) > 2}
    if not q_tokens:
        return 0.0
    text = content.lower()
    hits = sum(1 for t in q_tokens if t in text)
    return hits / len(q_tokens)
