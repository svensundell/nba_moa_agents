# Deployment runbook (live)

Runs locally and via Docker Compose, and now also on a public stack:
**Railway** (API + MCP), **Vercel** (frontend), and **Supabase** (Postgres + `pgvector`).

## Current status

The app is live:

- Frontend: `https://nba-moa-agents.vercel.app`
- Backend health: `https://nbamoaagents-production.up.railway.app/api/health`

The deployed setup uses BYOK (OpenRouter key entered by the visitor in the Access screen), Postgres on Supabase, and MCP servers started inside the Railway container.

A demo environment can be provisioned quickly when needed (new Railway service + Vercel project + Supabase instance, env vars, `alembic upgrade head`, smoke run). For a shared hosted demo, **bring-your-own-key** (visitor supplies an OpenRouter key in the UI or `X-OpenRouter-Key`) avoids billing LLM usage to the project owner; optional rate limits still apply per IP or app token.

This file stays as the runbook for reprovisioning / rollback / hardening.

## Target topology

```
                    ┌─────────────────────────────────────┐
                    │  Vercel — static React + rewrites   │
                    │  /api/*  ──proxy──▶  Railway API    │
                    │  /       SPA (index.html)           │
                    └──────────────────┬──────────────────┘
                                       │ HTTPS + WSS
                                       ▼
                    ┌─────────────────────────────────────┐
                    │  Railway — FastAPI + MCP subprocesses│
                    │  uvicorn :8000, health /api/health   │
                    └──────────────────┬──────────────────┘
                                       │ asyncpg
                                       ▼
                    ┌─────────────────────────────────────┐
                    │  Supabase — Postgres 15+ + pgvector   │
                    │  runs / agent_metrics / tool_calls    │
                    │  briefs / chunks (embeddings)         │
                    └─────────────────────────────────────┘
                                       │
                                       ▼
                              OpenRouter (LLM + embeddings)
                              ESPN / Reddit / balldontlie (via MCP)
```

Same separation as Docker Compose: browser talks to one origin; API and MCP stay on the backend container.

## Component mapping

| Piece | Local today | Production target |
|-------|-------------|-------------------|
| Frontend | Vite dev / nginx in Compose | **Vercel** — `npm run build`, SPA |
| API + WebSocket | FastAPI `:8000` | **Railway** — `backend/Dockerfile` |
| Database | `pgvector/pgvector:pg16` volume | **Supabase** — enable `vector` extension |
| MCP servers | Mounted `mcp_servers/` | Baked in image (already in Dockerfile) |
| Migrations | `AUTO_MIGRATE=true` on boot | **Release command**: `alembic upgrade head`; set `AUTO_MIGRATE=false` in prod |

## Supabase (database)

1. Create a project; run in SQL editor: `create extension if not exists vector;`
2. **Connection string** — from the dashboard **Connect** panel:
   - **Session pooler** (recommended for local dev and Railway): host `*.pooler.supabase.com`, user `postgres.[project-ref]`, port `5432`. Works on IPv4 networks where `db.*.supabase.co` (IPv6-only direct) fails with `ConnectionRefusedError`.
   - **Direct** (`db.[ref].supabase.co`): only if the network supports IPv6, or after enabling the IPv4 add-on.
3. Prefix with `postgresql+asyncpg://` (not `postgresql://`). Wrap the line in **double quotes** in `.env` if the password contains `#`, `/`, or `!`.
4. SSL is required; the backend sets `connect_args={"ssl": "require"}` when the host contains `supabase.co`.
5. Match `MEMORY_EMBEDDING_DIM` to the configured embedding model (default `1536` for `text-embedding-3-small`).
6. Run migrations once from a workstation or a Railway release phase:

```bash
cd backend
DATABASE_URL="postgresql+asyncpg://..." uv run alembic upgrade head
```

## Railway (backend)

**Service:** deploy from repo root. The repo includes `railway.json` (`builder: DOCKERFILE`, `dockerfilePath: backend/Dockerfile`, build context `.` — same as Compose). If Railpack fails with “could not determine start command”, click **Use backend Dockerfile** in the build error UI or set Dockerfile path to `backend/Dockerfile` in service settings.

**Required env vars:**

| Variable | Notes |
|----------|--------|
| `DATABASE_URL` | Supabase async URL |
| `ALLOWED_ORIGINS` | `https://<app>.vercel.app` |
| `APP_ENV` | `production` |
| `AUTO_MIGRATE` | `false` after first migrate |
| `MEMORY_ENABLED` | `true` if Copilot memory is on |
| `BALLDONTLIE_API_KEY` | Optional |

**Operational notes:**

- **Health check:** `GET /api/health` (includes `database_ok` after Postgres is reachable). The container must listen on Railway’s `$PORT` (see `backend/Dockerfile` — not a hardcoded `8000` only).
- **Cold start / MCP:** first request may take up to ~90s while three stdio MCP servers boot (same as local Docker healthcheck `start_period`).
- **WebSockets:** enable on Railway; proxy timeouts ≥ 3600s (nginx local config already uses long `proxy_read_timeout` for runs).
- **Scaling:** start with **one** replica — MoA runs are CPU/API heavy; horizontal scale needs sticky sessions or stateless redesign for in-flight WS.
- **Rollback:** redeploy previous Railway image; DB schema is forward-only via Alembic.

## Vercel (frontend)

Build: root directory `frontend`, command `npm run build`, output `dist`.

**Recommended (current production):** point the frontend straight at Railway (no reliance on Vercel rewrites).

**Vercel environment variable** (Production + Preview; then **Redeploy** — Vite bakes vars at build time):

| Variable | Value |
|----------|--------|
| `VITE_API_BASE` | `https://nbamoaagents-production.up.railway.app/api` |

WebSocket URL is derived automatically (`wss://…/api`). Optional override: `VITE_WS_API_BASE`.

**Railway:** `ALLOWED_ORIGINS` must list every Vercel origin with `https://` (comma-separated, no trailing slash), e.g. `https://nba-moa-agents.vercel.app,https://nba-moa-agents-git-main-….vercel.app`.

`frontend/vercel.json` rewrites are optional if `VITE_API_BASE` is set.

**Verify in the browser:** DevTools → Network → filter **WS** → run a pipeline → Request URL must be `wss://nbamoaagents-production.up.railway.app/api/ws/run`. Or Sources → search `railway.app` in the built JS bundle.

## Secrets and config

| Secret | Where |
|--------|--------|
| `DATABASE_URL` | Railway only |
| `BALLDONTLIE_API_KEY` | Railway only |
| Public URLs | Vercel env via `VITE_API_BASE` (production and preview) |

Do not commit `.env`. Store secrets in Railway/Vercel dashboards; rotate keys if a demo URL is shared widely.

## Public demo controls

For a hosted URL with real agent runs:

| Control | Purpose |
|---------|---------|
| **Bring-your-own-key** | Visitor passes OpenRouter key via Access screen or `X-OpenRouter-Key`; LLM cost stays on their account |
| **Auth gate** | Optional: API key, HTTP Basic, or Clerk/Auth0 on `/api/*` before runs execute |
| **Rate limit** | e.g. SlowAPI: N runs / hour per IP or per supplied API key |
| **Daily quota** | Postgres or Redis counter per identity |
| **Fixture demo mode** | `DEMO_MODE` serves frozen `RunResult` JSON — no LLM/MCP (portfolio walkthrough without keys) |
| **Mode restrictions** | e.g. Copilot-only on public tier; disable `compare` to halve parallel cost |

Implementation sketch (not in repo): middleware accepts `X-OpenRouter-Key` or falls back to server env; `DEMO_MODE=true` returns fixtures.

## Caching (optional)

| Cache | What |
|-------|------|
| **HTTP** | Short TTL on ESPN/RSS inside MCP servers — fewer duplicate tool calls per run |
| **Redis** | Rate-limit counters; optional embedding cache for hot memory queries |

Optional for low-traffic demos.

## Time to deploy (estimate)

| Step | Effort |
|------|--------|
| Supabase project + `vector` + migrations | ~15 min |
| Railway service from `backend/Dockerfile`, env vars | ~20 min |
| Vercel project + `VITE_API_BASE` | ~10 min |
| WebSocket smoke test (one Brief) | ~5 min |

No application refactor required — only infrastructure and env configuration.

## Observability in production

| Signal | Approach |
|--------|----------|
| **Uptime** | Railway health + external ping on `/api/health` |
| **Run metrics** | Existing Postgres eval tables + Evaluation UI ([`llmops.md`](llmops.md)) |
| **Errors** | Structured logs (`LOG_LEVEL=INFO`); optional Sentry on FastAPI |
| **LLM traces** | Optional Langfuse callback on `RunTracker` flush — same events as today |

## Promotion flow (dev → demo)

```
local (make dev)  →  PR (CI)  →  merge main
       →  Railway staging (optional)  →  alembic upgrade head
       →  Railway production  →  Vercel production alias
```

- **CI** already blocks broken builds ([`testing.md`](testing.md)).
- **DB:** never auto-migrate prod from app boot if multiple replicas — use release job only.
- **Rollback:** Railway previous deployment + Vercel instant rollback; DB migrations may need a down revision if schema changed.

## Checklist before sharing a public URL

- [x] Supabase `vector` extension enabled; migrations applied
- [x] Railway env set; `ALLOWED_ORIGINS` matches Vercel URL
- [x] Vercel connected to Railway API (`VITE_API_BASE`); WebSocket smoke test passed
- [x] BYOK enabled (visitor key in Access screen)
- [ ] Optional: auth/rate-limit policy for public traffic
- [ ] Optional: OpenRouter budget alert if a shared key is ever enabled
- [ ] `AUTO_MIGRATE=false` in production (after initial migration bootstrap)
