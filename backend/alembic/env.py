"""Alembic environment config."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import connect_args_for_url
from app.eval import models as _eval_models  # noqa: F401
from app.memory import models as _memory_models  # noqa: F401

config = context.config
settings = get_settings()
# Do not pass DATABASE_URL through config.set_main_option — ConfigParser treats
# '%' in URL-encoded passwords as interpolation syntax.
database_url = settings.database_url

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    async def _run() -> None:
        connectable = create_async_engine(
            database_url,
            poolclass=pool.NullPool,
            connect_args=connect_args_for_url(database_url),
        )
        async with connectable.connect() as connection:
            await connection.run_sync(_do_run_migrations)
        await connectable.dispose()

    asyncio.run(_run())


def _do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
