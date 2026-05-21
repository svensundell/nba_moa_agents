"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app import __version__
from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import close_engine, configure_engine, get_session_factory, ping, upgrade_head
from app.eval.repository import configure_repository as configure_eval_repository
from app.mcp.client import mcp_registry
from app.memory import configure_memory
from app.memory.repository import configure_repository as configure_memory_repository


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise DB, repositories, and MCP registry at boot.

    All three MCP servers (nba_stats, reddit, espn) are spawned as stdio
    subprocesses via ``MultiServerMCPClient``. Their tool schemas are loaded
    eagerly so agents can look them up by name throughout the request cycle.

    Persistence uses Postgres (plus pgvector for memory embeddings) via
    SQLAlchemy async sessions. Pending Alembic revisions are applied on
    startup when ``AUTO_MIGRATE=true`` (default).
    """
    settings = get_settings()
    try:
        if settings.auto_migrate:
            await upgrade_head()
        configure_engine(settings.database_url, echo=settings.db_echo)
        session_factory = get_session_factory()
        eval_repo = configure_eval_repository(session_factory)
        memory_repo = configure_memory_repository(session_factory)
        memory = configure_memory(memory_repo)
        await ping()
        await eval_repo.initialize()
        await memory.initialize()
    except Exception as exc:  # pragma: no cover - depends on network/filesystem
        logger.error(f"Repository initialisation failed: {exc}")
        raise

    try:
        await mcp_registry.initialize()
    except Exception as exc:  # pragma: no cover - depends on subprocesses
        logger.error(f"MCP initialisation failed: {exc}")
        await eval_repo.close()
        await memory.close()
        await close_engine()
        raise
    try:
        yield
    finally:
        await mcp_registry.shutdown()
        await eval_repo.close()
        await memory.close()
        await close_engine()


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="NBA MCP & Mixture of Agents",
        version=__version__,
        description=(
            "Mixture-of-Agents pipeline for NBA briefings & queries. "
            "Built with LangGraph + OpenRouter + MCP."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")

    @app.get("/")
    async def root() -> dict:
        return {
            "name": "nba-moa-agents",
            "version": __version__,
            "docs": "/docs",
            "endpoints": [
                "/api/brief",
                "/api/query",
                "/api/compare",
                "/api/ws/run",
                "/api/runs",
                "/api/runs/{run_id}",
                "/api/metrics/summary",
                "/api/memory/briefs",
                "/api/memory/search",
            ],
        }

    return app


app = create_app()
