"""SQLAlchemy models for brief memory + pgvector search."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db import Base

EMBEDDING_DIM = get_settings().memory_embedding_dim


class BriefRow(Base):
    __tablename__ = "briefs"

    brief_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    date: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    chunk_count: Mapped[int] = mapped_column(nullable=False, default=0)

    chunks: Mapped[list[ChunkRow]] = relationship(
        back_populates="brief", cascade="all, delete-orphan"
    )


class ChunkRow(Base):
    __tablename__ = "chunks"

    chunk_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    brief_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("briefs.brief_id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[str] = mapped_column(String(32), nullable=False)
    section: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    brief: Mapped[BriefRow] = relationship(back_populates="chunks")
