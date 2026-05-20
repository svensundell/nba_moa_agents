"""Run Alembic migrations programmatically (async-safe for FastAPI startup)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from loguru import logger
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.eval import models as _eval_models  # noqa: F401
from app.memory import models as _memory_models  # noqa: F401

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def _run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    cfg = _alembic_config()
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        config=cfg,
    )
    with context.begin_transaction():
        context.run_migrations()


async def upgrade_head() -> None:
    """Apply all pending Alembic revisions (``alembic upgrade head``)."""
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
        logger.info("Database migrations applied (alembic upgrade head)")
    finally:
        await engine.dispose()
