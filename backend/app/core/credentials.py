"""Per-request OpenRouter key (BYOK) and optional app access token."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import HTTPException, status
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine

_openrouter_api_key: ContextVar[str | None] = ContextVar("openrouter_api_key", default=None)


async def resolve_openrouter_api_key(header_key: str | None = None) -> str:
    """Pick the OpenRouter key for this request (header, WS payload, or request context)."""
    if header_key and header_key.strip():
        return header_key.strip()
    override = _openrouter_api_key.get()
    if override and override.strip():
        return override.strip()
    settings = get_settings()
    sponsored_key = settings.demo_openrouter_key.get_secret_value().strip()
    if sponsored_key:
        # Reserve before billing, including concurrent requests and failed runs.
        async with get_engine().begin() as conn:
            reserved = await conn.scalar(
                text("""
                    INSERT INTO demo_usage (day, requests)
                    VALUES ((CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date, 1)
                    ON CONFLICT (day) DO UPDATE SET requests = demo_usage.requests + 1
                    WHERE demo_usage.requests < :limit
                    RETURNING requests
                """),
                {"limit": settings.demo_daily_runs},
            )
        if reserved is None:
            raise HTTPException(
                status_code=429, detail="Daily demo limit reached. Try again tomorrow (UTC)."
            )
        return sponsored_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="OpenRouter API key required. Send header X-OpenRouter-Key or openrouter_api_key in the WebSocket handshake.",
    )


@contextmanager
def use_openrouter_api_key(key: str) -> Iterator[str]:
    """Bind a resolved key for the current async task (LLM + embeddings)."""
    token = _openrouter_api_key.set(key)
    try:
        yield key
    finally:
        _openrouter_api_key.reset(token)


def openrouter_key_for_llm() -> str:
    """Return the active OpenRouter key (must run inside use_openrouter_api_key)."""
    override = _openrouter_api_key.get()
    if override and override.strip():
        return override.strip()
    raise RuntimeError(
        "OpenRouter API key is not set. Provide X-OpenRouter-Key or openrouter_api_key in the WebSocket handshake."
    )


def verify_app_access(
    *,
    header_token: str | None = None,
    authorization: str | None = None,
) -> None:
    """When APP_ACCESS_TOKEN is configured, require a matching bearer or X-App-Access-Token."""
    settings = get_settings()
    expected = settings.app_access_token.strip()
    if not expected:
        return

    provided = (header_token or "").strip()
    if not provided and authorization:
        scheme, _, cred = authorization.partition(" ")
        if scheme.lower() == "bearer" and cred.strip():
            provided = cred.strip()

    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing app access token.",
        )
