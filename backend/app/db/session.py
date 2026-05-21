"""Async SQLAlchemy engine/session helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def connect_args_for_url(database_url: str) -> dict[str, object]:
    """Driver extras for hosted Postgres (Supabase requires SSL)."""
    if "supabase.co" in database_url:
        return {"ssl": "require"}
    return {}


def configure_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Configure (or replace) the shared async engine."""
    global _engine, _session_factory
    _engine = create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        connect_args=connect_args_for_url(database_url),
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("SQLAlchemy engine is not configured.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("SQLAlchemy session factory is not configured.")
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield an async session and close it safely."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        await session.close()


async def ping() -> None:
    """Validate DB connectivity."""
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def close_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
