"""HTTP and WebSocket routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
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
from app.mcp.client import mcp_registry
from app.moa.llm import AGENT_MODELS, MODEL_REGISTRY, model_id

router = APIRouter()


def _normalise_language(language: str | None) -> str:
    value = (language or "en").strip().lower()
    return value if value in {"en", "fr"} else "en"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        has_openrouter=settings.has_openrouter,
        has_balldontlie=settings.has_balldontlie,
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
