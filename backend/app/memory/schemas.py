"""Pydantic models for brief memory storage and retrieval."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BriefSummary(BaseModel):
    brief_id: str
    run_id: str
    date: str
    language: str = "en"
    title: str = ""
    chunk_count: int = 0
    indexed_at: datetime


class MemoryChunkHit(BaseModel):
    chunk_id: str
    brief_id: str
    date: str
    section: str
    content: str
    score: float = Field(description="Similarity or keyword relevance score in [0, 1].")


class MemorySearchResult(BaseModel):
    query: str
    days: int
    hits: list[MemoryChunkHit] = Field(default_factory=list)


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1)
    days: int = Field(default=14, ge=1, le=365)
    limit: int = Field(default=6, ge=1, le=20)
