"""HTTP and WebSocket routes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import aclosing, asynccontextmanager
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from loguru import logger
from pydantic import ValidationError

from app.api.account import check_origin, current_owner, require_owner
from app.api.runner import run_full, run_streaming
from app.api.schemas import (
    BriefRequest,
    CompareRequest,
    HealthResponse,
    QueryRequest,
    RunResult,
)
from app.core.config import get_settings
from app.core.credentials import (
    demo_runs_remaining,
    resolve_openrouter_api_key,
    use_openrouter_api_key,
    verify_app_access,
)
from app.db.session import ping as db_ping
from app.eval.repository import get_repository
from app.eval.schemas import DashboardSummary, RunSummary
from app.mcp.client import mcp_registry
from app.memory import get_memory_service
from app.memory.schemas import BriefSummary, MemorySearchRequest, MemorySearchResult
from app.moa.llm import AGENT_MODELS, MODEL_REGISTRY, model_id

router = APIRouter()


Owner = Annotated[str, Depends(require_owner)]
RUN_TIMEOUT = 120


def _require_run_access(
    request: Request,
    x_openrouter_key: str | None = Header(default=None, alias="X-OpenRouter-Key"),
    x_app_access_token: str | None = Header(default=None, alias="X-App-Access-Token"),
    authorization: str | None = Header(default=None),
) -> str | None:
    check_origin(request)
    verify_app_access(header_token=x_app_access_token, authorization=authorization)
    return x_openrouter_key


@asynccontextmanager
async def _run_access(api_key: str | None) -> AsyncIterator[None]:
    try:
        async with asyncio.timeout(RUN_TIMEOUT):
            with use_openrouter_api_key(await resolve_openrouter_api_key(api_key)):
                yield
    except TimeoutError:
        raise HTTPException(504, "The run exceeded its time limit.") from None


@router.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    settings = get_settings()
    response.headers["Cache-Control"] = "no-store"
    sponsored = bool(settings.demo_openrouter_key.get_secret_value().strip())
    remaining = None
    database_ok = False
    try:
        await db_ping()
        if sponsored:
            remaining = await demo_runs_remaining(settings.demo_daily_runs)
        database_ok = True
    except Exception:
        database_ok = False
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        openrouter_byok=True,
        sponsored_runs=sponsored,
        demo_daily_runs=settings.demo_daily_runs if sponsored else None,
        demo_runs_remaining=remaining,
        has_balldontlie=settings.has_balldontlie,
        database_ok=database_ok,
        mcp_initialised=mcp_registry.initialised,
        mcp_servers=mcp_registry.server_names,
        mcp_tools=mcp_registry.tool_names,
        app_access_required=bool(settings.app_access_token.strip()),
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
async def brief(
    req: BriefRequest,
    request: Request,
    api_key: str | None = Depends(_require_run_access),
) -> RunResult:
    async with _run_access(api_key):
        return await run_full(
            "brief",
            date=req.date.isoformat() if req.date else None,
            language=req.language,
            owner_id=current_owner(request),
        )


@router.post("/query", response_model=RunResult)
async def query(
    req: QueryRequest,
    request: Request,
    api_key: str | None = Depends(_require_run_access),
) -> RunResult:
    async with _run_access(api_key):
        return await run_full(
            "query",
            query=req.messages[-1].content if req.messages else req.query,
            messages=[m.model_dump(mode="json") for m in req.messages],
            date=req.date.isoformat() if req.date else None,
            language=req.language,
            owner_id=current_owner(request),
        )


@router.post("/compare", response_model=RunResult)
async def compare(
    req: CompareRequest,
    request: Request,
    api_key: str | None = Depends(_require_run_access),
) -> RunResult:
    async with _run_access(api_key):
        return await run_full(
            "compare",
            query=req.query,
            date=req.date.isoformat() if req.date else None,
            language=req.language,
            owner_id=current_owner(request),
        )


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(
    owner: Owner,
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
    return await repo.list_runs(owner_id=owner, limit=limit, mode=mode)


@router.get("/runs/{run_id}", response_model=RunResult)
async def get_run(run_id: str, owner: Owner) -> RunResult:
    """Return the full :class:`RunResult` payload for a persisted run."""
    try:
        repo = get_repository()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    payload = await repo.get_run_payload(run_id, owner_id=owner)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return RunResult.model_validate(payload)


@router.get("/metrics/summary", response_model=DashboardSummary)
async def metrics_summary(
    owner: Owner,
    last_n: int = Query(default=100, ge=1, le=1000),
    mode: str | None = Query(default=None, pattern="^(brief|query|compare)$"),
) -> DashboardSummary:
    """Aggregates rendered on the evaluation dashboard landing card."""
    try:
        repo = get_repository()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return await repo.summary(owner_id=owner, last_n=last_n, mode=mode)


@router.get("/memory/briefs", response_model=list[BriefSummary])
async def list_memory_briefs(
    owner: Owner,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[BriefSummary]:
    """Indexed Daily Briefs available to NBA Copilot memory search."""
    try:
        memory = get_memory_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return await memory.list_briefs(limit=limit, owner_id=owner)


@router.post("/memory/search", response_model=MemorySearchResult)
async def search_memory(
    req: MemorySearchRequest,
    owner: Owner,
    api_key: str | None = Depends(_require_run_access),
) -> MemorySearchResult:
    """Semantic search over archived Daily Brief chunks (debug / UI)."""
    try:
        memory = get_memory_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    async with _run_access(api_key):
        return await memory.search(req.query, days=req.days, limit=req.limit, owner_id=owner)


@router.delete("/runs", status_code=204)
async def clear_history(request: Request, owner: Owner) -> Response:
    check_origin(request)
    await get_repository().clear_history(owner)
    return Response(status_code=204, headers={"Cache-Control": "private, no-store"})


async def _send_run(websocket: WebSocket) -> None:
    raw = await asyncio.wait_for(websocket.receive_text(), timeout=15)
    if len(raw.encode()) > 24_000:
        raise ValueError("Request too large")
    payload = json.loads(raw)
    mode = payload.get("mode", "brief")
    if mode == "query":
        query_req = QueryRequest.model_validate(payload)
        req: BriefRequest = query_req
        query = query_req.messages[-1].content if query_req.messages else query_req.query
        messages = [m.model_dump(mode="json") for m in query_req.messages]
    elif mode == "brief":
        req = BriefRequest.model_validate(payload)
        query, messages = "", None
    elif mode == "compare":
        compare_req = CompareRequest.model_validate(payload)
        req = compare_req
        query, messages = compare_req.query, None
    else:
        raise ValueError("Unknown mode")

    verify_app_access(header_token=str(payload.get("app_access_token") or ""))
    api_key = await resolve_openrouter_api_key(str(payload.get("openrouter_api_key") or ""))
    with use_openrouter_api_key(api_key):
        async with aclosing(
            run_streaming(
                mode,
                query=query,
                messages=messages,
                date=req.date.isoformat() if req.date else None,
                language=req.language,
                owner_id=current_owner(websocket),
            )
        ) as frames:
            async for frame in frames:
                await websocket.send_json(frame)


@router.websocket("/ws/run")
async def ws_run(websocket: WebSocket) -> None:
    try:
        check_origin(websocket)
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        async with asyncio.timeout(RUN_TIMEOUT):
            await _send_run(websocket)
    except WebSocketDisconnect:
        return
    except (ValueError, ValidationError, AttributeError):
        await websocket.send_json(
            {"kind": "error", "code": "invalid", "message": "Invalid run request."}
        )
    except HTTPException as exc:
        code = {429: "quota", 401: "access"}.get(exc.status_code, "generation")
        await websocket.send_json({"kind": "error", "code": code, "message": str(exc.detail)})
    except TimeoutError:
        await websocket.send_json({"kind": "error", "code": "timeout", "message": "Run timed out."})
    except Exception as exc:
        logger.warning("WebSocket run failed ({})", type(exc).__name__)
        await websocket.send_json({"kind": "error", "code": "generation", "message": "Run failed."})
    await websocket.close()
