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
from app.eval.repository import configure_repository
from app.mcp.client import mcp_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the MCP registry and the eval repository at boot.

    All three MCP servers (nba_stats, reddit, espn) are spawned as stdio
    subprocesses via ``MultiServerMCPClient``. Their tool schemas are loaded
    eagerly so agents can look them up by name throughout the request cycle.

    The eval repository owns a long-lived aiosqlite connection that
    serves the run-history endpoints under ``/api/runs`` and
    ``/api/metrics/summary``. Persistence failures are isolated from the
    main pipeline by the runner layer.
    """
    settings = get_settings()
    repo = configure_repository(settings.resolved_eval_db_path)
    try:
        await repo.initialize()
    except Exception as exc:  # pragma: no cover - depends on filesystem
        logger.error(f"Eval repository initialisation failed: {exc}")
        raise

    try:
        await mcp_registry.initialize()
    except Exception as exc:  # pragma: no cover - depends on subprocesses
        logger.error(f"MCP initialisation failed: {exc}")
        await repo.close()
        raise
    try:
        yield
    finally:
        await mcp_registry.shutdown()
        await repo.close()


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="NBA Mixture of Agents",
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
            ],
        }

    return app


app = create_app()
