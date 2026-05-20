"""HTTP and WebSocket routes."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from loguru import logger

from app.api.runner import run_full, run_streaming
from app.api.schemas import (
    BriefRequest,
    CompareRequest,
    HealthResponse,
    QueryRequest,
    RunResult,
)
from app.core.config import get_settings
from app.db.session import ping as db_ping
from app.eval.repository import get_repository
from app.eval.schemas import DashboardSummary, RunSummary
from app.mcp.client import mcp_registry
from app.memory import get_memory_service
from app.memory.schemas import BriefSummary, MemorySearchRequest, MemorySearchResult
from app.moa.llm import AGENT_MODELS, MODEL_REGISTRY, model_id

router = APIRouter()


def _normalise_language(language: str | None) -> Literal["en", "fr"]:
    value = (language or "en").strip().lower()
    return "fr" if value == "fr" else "en"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    database_ok = False
    try:
        await db_ping()
        database_ok = True
    except Exception:
        database_ok = False
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        has_openrouter=settings.has_openrouter,
        has_balldontlie=settings.has_balldontlie,
        database_ok=database_ok,
        mcp_initialised=mcp_registry.initialised,
        mcp_servers=mcp_registry.server_names,
        mcp_tools=mcp_registry.tool_names,
    )


@router.get("/agents")
async def agents() -> dict:
    """Expose the agent → model mapping so the frontend can label nodes."""
    return {
        "agents": [
            {
                "agent": agent,
                "logical_model": logical,
                "provider_model": model_id(logical),
                "description": MODEL_REGISTRY[logical].description,
            }
            for agent, logical in AGENT_MODELS.items()
        ]
    }


@router.post("/brief", response_model=RunResult)
async def brief(req: BriefRequest) -> RunResult:
    return await run_full("brief", date=req.date, language=_normalise_language(req.language))


@router.post("/query", response_model=RunResult)
async def query(req: QueryRequest) -> RunResult:
    if not req.messages and not req.query.strip():
        raise HTTPException(status_code=422, detail="Provide `query` or non-empty `messages`.")
    return await run_full(
        "query",
        query=req.query,
        messages=[m.model_dump(mode="json") for m in req.messages],
        date=req.date,
        language=_normalise_language(req.language),
    )


@router.post("/compare", response_model=RunResult)
async def compare(req: CompareRequest) -> RunResult:
    return await run_full(
        "compare",
        query=req.query,
        date=req.date,
        language=_normalise_language(req.language),
    )


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(
    limit: int = Query(default=50, ge=1, le=500),
    mode: str | None = Query(default=None, pattern="^(brief|query|compare)$"),
) -> list[RunSummary]:
    """List the most recent persisted runs.

    Filters by ``mode`` and caps the result set at ``limit`` rows (max
    500). Used by the evaluation dashboard to render the history table
    and the cost/latency charts.
    """
    try:
        repo = get_repository()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return await repo.list_runs(limit=limit, mode=mode)


@router.get("/runs/{run_id}", response_model=RunResult)
async def get_run(run_id: str) -> RunResult:
    """Return the full :class:`RunResult` payload for a persisted run."""
    try:
        repo = get_repository()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    payload = await repo.get_run_payload(run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return RunResult.model_validate(payload)


@router.get("/metrics/summary", response_model=DashboardSummary)
async def metrics_summary(
    last_n: int = Query(default=100, ge=1, le=1000),
    mode: str | None = Query(default=None, pattern="^(brief|query|compare)$"),
) -> DashboardSummary:
    """Aggregates rendered on the evaluation dashboard landing card."""
    try:
        repo = get_repository()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return await repo.summary(last_n=last_n, mode=mode)


@router.get("/memory/briefs", response_model=list[BriefSummary])
async def list_memory_briefs(
    limit: int = Query(default=50, ge=1, le=200),
) -> list[BriefSummary]:
    """Indexed Daily Briefs available to NBA Copilot memory search."""
    try:
        memory = get_memory_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return await memory.list_briefs(limit=limit)


@router.post("/memory/search", response_model=MemorySearchResult)
async def search_memory(req: MemorySearchRequest) -> MemorySearchResult:
    """Semantic search over archived Daily Brief chunks (debug / UI)."""
    try:
        memory = get_memory_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return await memory.search(req.query, days=req.days, limit=req.limit)


@router.websocket("/ws/run")
async def ws_run(websocket: WebSocket) -> None:
    """Streaming endpoint — the frontend uses this to watch agents work live.

    Protocol:
      Client sends one JSON frame: {"mode": "brief|query|compare",
                                    "query": "...", "date": "..."}
      Server streams JSON frames as documented in ``run_streaming``.
    """
    await websocket.accept()
    try:
        msg = await websocket.receive_text()
        payload = json.loads(msg)
        mode = payload.get("mode", "brief")
        if mode not in {"brief", "query", "compare"}:
            await websocket.send_json({"kind": "error", "message": f"unknown mode {mode}"})
            await websocket.close()
            return
        if (
            mode == "query"
            and not str(payload.get("query", "")).strip()
            and not payload.get("messages")
        ):
            await websocket.send_json(
                {"kind": "error", "message": "Provide `query` or non-empty `messages`."}
            )
            await websocket.close()
            return

        async for frame in run_streaming(
            mode,
            query=payload.get("query", ""),
            messages=payload.get("messages"),
            date=payload.get("date"),
            language=_normalise_language(str(payload.get("language", "en"))),
        ):
            await websocket.send_json(frame)

        await websocket.close()
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        logger.exception(f"WebSocket failed: {exc}")
        try:
            await websocket.send_json({"kind": "error", "message": str(exc)})
        except Exception:
            pass
        await websocket.close()
