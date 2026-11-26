"""Session and ownership checks without a real Google account or LLM."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlencode

import pytest
from authlib.integrations.base_client import OAuthError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from starlette.responses import RedirectResponse

from app.api import account
from app.core.config import get_settings
from app.eval.models import RunRow
from app.eval.repository import configure_repository as configure_eval
from app.eval.tracker import RunTracker
from app.main import create_app
from app.memory.repository import configure_repository as configure_archive
from app.memory.service import configure_memory

ORIGIN = "https://nba.test"


@pytest.fixture
def app_with_google(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("SESSION_SECRET", "test-cookie-key-with-at-least-32-characters")
    monkeypatch.setenv("PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("SERVE_FRONTEND", "false")
    get_settings.cache_clear()
    app = create_app()
    try:
        yield app
    finally:
        get_settings.cache_clear()


@pytest.fixture
def google_stub(monkeypatch):
    async def authorize(request, redirect_uri):
        assert redirect_uri == ORIGIN + "/api/account/google/callback"
        request.session["state"] = "test-state"
        return RedirectResponse("https://google.test/?state=test-state")

    async def exchange(request):
        if request.session.get("state") != request.query_params.get("state") or not request.session:
            raise OAuthError("state_mismatch")
        return {"userinfo": {"sub": request.query_params["code"]}}

    google = Mock(
        authorize_redirect=AsyncMock(side_effect=authorize),
        authorize_access_token=AsyncMock(side_effect=exchange),
    )
    monkeypatch.setattr(account, "_google", lambda: Mock(create_client=lambda _: google))


async def _login(client, subject):
    start = await client.get("/api/account/google")
    assert start.headers["location"] == "https://google.test/?state=test-state"
    result = await client.get(
        "/api/account/google/callback?" + urlencode({"state": "test-state", "code": subject})
    )
    assert result.headers["location"] == "/?view=history"
    assert "HttpOnly" in result.headers.get_list("set-cookie")[0]
    assert "Secure" in result.headers.get_list("set-cookie")[0]
    assert (await client.get("/api/account/session")).json() == {
        "google_sign_in": True,
        "signed_in": True,
    }


async def test_google_session_rejects_missing_state_and_logs_out(app_with_google, google_stub):
    async with AsyncClient(transport=ASGITransport(app=app_with_google), base_url=ORIGIN) as client:
        callback = "/api/account/google/callback?state=test-state&code=alice"
        assert (await client.get(callback)).headers["location"] == "/?account=error"
        await _login(client, "alice")
        assert (
            await client.post("/api/account/logout", headers={"Origin": "https://other.test"})
        ).status_code == 403
        assert (
            await client.post("/api/account/logout", headers={"Origin": ORIGIN})
        ).status_code == 204
        assert not (await client.get("/api/account/session")).json()["signed_in"]
        assert (await client.get("/api/runs")).status_code == 401
        assert (await client.get(callback)).headers["location"] == "/?account=error"


async def test_private_runs_metrics_and_memory_are_scoped(
    app_with_google,
    google_stub,
    pg_session_factory,
):
    repo = configure_eval(pg_session_factory)
    archive = configure_archive(pg_session_factory)
    configure_memory(archive)
    today = date.today().isoformat()

    async def save(client, subject):
        await _login(client, subject)
        signed_cookie = client.cookies.get("__Host-nba_account")
        owner = account._serializer().loads(signed_cookie)
        metrics = RunTracker(mode="brief").finalize()
        await repo.save_run(
            metrics=metrics,
            owner_id=owner,
            date=today,
            language="en",
            query=subject,
            final_brief=subject,
            single_llm_answer="",
            payload={
                "mode": "brief",
                "date": today,
                "query": subject,
                "final_brief": subject,
                "started_at": metrics.started_at.isoformat(),
                "finished_at": metrics.finished_at.isoformat(),
                "duration_seconds": metrics.duration_seconds,
            },
        )
        await archive.upsert_brief(
            brief_id=metrics.run_id,
            run_id=metrics.run_id,
            date_value=today,
            language="en",
            title=subject,
            body_markdown=subject,
            chunks=[("summary", subject, None)],
            owner_id=owner,
        )
        return metrics.run_id, owner

    transport = ASGITransport(app=app_with_google)
    async with (
        AsyncClient(transport=transport, base_url=ORIGIN) as first,
        AsyncClient(transport=transport, base_url=ORIGIN) as second,
        AsyncClient(transport=transport, base_url=ORIGIN) as guest,
    ):
        first_id, first_owner = await save(first, "alice")
        second_id, second_owner = await save(second, "bob")
        legacy_id, _ = await save(guest, "legacy")
        guest.cookies.clear()
        async with pg_session_factory.begin() as db:
            await db.execute(update(RunRow).where(RunRow.run_id == legacy_id).values(owner_id=None))
        assert first_owner != second_owner
        for path in (
            "/api/runs",
            f"/api/runs/{first_id}",
            "/api/metrics/summary",
            "/api/memory/briefs",
        ):
            denied = await guest.get(path)
            assert denied.status_code == 401
            assert denied.headers["cache-control"] == "private, no-store"

        own = await first.get(f"/api/runs/{first_id}")
        assert own.json()["query"] == "alice"
        assert own.headers["cache-control"] == "private, no-store"
        assert (await first.get(f"/api/runs/{second_id}")).status_code == 404
        assert (await first.get(f"/api/runs/{legacy_id}")).status_code == 404
        assert [r["run_id"] for r in (await second.get("/api/runs")).json()] == [second_id]
        assert (await second.get("/api/metrics/summary")).json()["total_runs"] == 1
        assert [r["title"] for r in (await first.get("/api/memory/briefs")).json()] == ["alice"]
        assert [
            r["content"]
            for r in await archive.fetch_chunks_for_search(days=7, owner_id=second_owner)
        ] == ["bob"]
        assert (await first.delete("/api/runs", headers={"Origin": ORIGIN})).status_code == 204
        assert (await first.get("/api/memory/briefs")).json() == []
        assert [r["run_id"] for r in (await second.get("/api/runs")).json()] == [second_id]
