# Postgres + pgvector migration runbook

Step-by-step guide to run the app on Postgres after the SQLAlchemy/Alembic migration.

**Two paths:**

| Path | When to use |
|------|-------------|
| [A — Fresh install](#path-a-fresh-install-no-legacy-sqlite) | New clone, empty DB, no `data/eval.db` |
| [B — Cutover from SQLite](#path-b-cutover-from-legacy-sqlite) | You already ran the app with `data/eval.db` / `data/memory.db` |

---

## Prerequisites

- Docker + Docker Compose v2 (for Postgres; recommended)
- Python 3.11+ with project deps (`uv sync --directory backend --extra dev` or `pip install -e ".[dev]"` in `backend/`)
- `.env` at repo root with at least `OPENROUTER_API_KEY` and `DATABASE_URL`

Default `DATABASE_URL` (Postgres exposed on host port 5432):

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/nba
```

Legacy SQLite paths (only for path B):

```env
EVAL_DB_PATH=data/eval.db
MEMORY_DB_PATH=data/memory.db
```

---

## Path A — Fresh install (no legacy SQLite)

### 1. Configure environment

```bash
cd /path/to/nba_moa_agents
cp .env.example .env
# Edit .env: set OPENROUTER_API_KEY=...
```

### 2. Start Postgres only

```bash
docker compose up -d postgres
docker compose ps postgres
# Wait until STATUS is healthy
```

### 3. Apply schema (Alembic)

Run from the host (Alembic files live under `backend/`; the backend Docker image does not bundle them yet).

```bash
cd backend
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/nba
alembic upgrade head
```

Expected: revision `20260520_000001` applied; tables `runs`, `agent_metrics`, `tool_calls`, `briefs`, `chunks`, and extension `vector`.

Quick check:

```bash
docker compose exec postgres psql -U postgres -d nba -c "\dt"
docker compose exec postgres psql -U postgres -d nba -c "\dx" | grep vector
```

### 4. Start the full stack

**Option 1 — Docker (UI + API)**

```bash
cd /path/to/nba_moa_agents
docker compose up --build
```

| URL | Check |
|-----|-------|
| http://127.0.0.1:8001/api/health | `status: ok`, MCP initialised |
| http://localhost:5173 | Web UI |

**Option 2 — Local backend + Docker Postgres**

```bash
# Terminal 1 — backend (from repo root)
cd backend
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/nba
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (Vite proxies `/api` to port 8000).

### 5. Smoke test (no LLM cost)

```bash
curl -s http://127.0.0.1:8001/api/health | python3 -m json.tool
curl -s "http://127.0.0.1:8001/api/runs?limit=5" | python3 -m json.tool
curl -s "http://127.0.0.1:8001/api/memory/briefs" | python3 -m json.tool
curl -s "http://127.0.0.1:8001/api/metrics/summary?last_n=10" | python3 -m json.tool
```

Use port **8000** instead of **8001** if you run uvicorn locally.

### 6. Smoke test (with LLM — validates persistence + memory)

In the UI:

1. Run **Daily Brief** once → creates rows in `runs` and indexes `briefs` / `chunks`.
2. Open **NBA Copilot** and ask: *Why is everyone talking about the Pacers this week?*  
   → Copilot may call `search_brief_memory` if prior briefs exist.

Or via API:

```bash
curl -s -X POST http://127.0.0.1:8001/api/brief \
  -H "Content-Type: application/json" \
  -d '{"language":"en"}' | python3 -m json.tool

curl -s -X POST http://127.0.0.1:8001/api/memory/search \
  -H "Content-Type: application/json" \
  -d '{"query":"Pacers storyline","days":14,"limit":5}' | python3 -m json.tool
```

---

## Path B — Cutover from legacy SQLite

Use this if you already have history under `data/eval.db` and/or `data/memory.db`.

### 1–3. Same as Path A

Configure `.env`, start Postgres, run `alembic upgrade head`.

### 4. Backfill into Postgres

From `backend/` with `DATABASE_URL` pointing at Postgres:

```bash
cd backend
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/nba
# Optional overrides if files are not at data/*.db
export EVAL_DB_PATH=/path/to/nba_moa_agents/data/eval.db
export MEMORY_DB_PATH=/path/to/nba_moa_agents/data/memory.db

uv run python -m scripts.migrate_sqlite_to_postgres
```

The script logs counts like `Migrated runs: N` and `Migrated briefs: M`. Re-running is safe for eval runs (upsert by `run_id`); memory skips briefs that already exist unless you force re-index via the API.

### 5. Optional — reindex memory from eval DB only

If you skipped legacy `memory.db` but have brief runs in eval:

```bash
curl -s -X POST "http://127.0.0.1:8001/api/memory/reindex?limit=100"
```

Requires `OPENROUTER_API_KEY` (embeddings).

### 6. Start app + smoke test

Follow [Path A §4–6](#4-start-the-full-stack).

Verify data landed:

```bash
curl -s "http://127.0.0.1:8001/api/runs?limit=5&mode=brief"
curl -s "http://127.0.0.1:8001/api/memory/briefs"
```

---

## Running tests against Postgres

Repository integration tests need a real Postgres instance:

```bash
docker compose up -d postgres
cd backend
export TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/nba_test

# Create empty test DB once
docker compose exec postgres psql -U postgres -c "CREATE DATABASE nba_test;"

export DATABASE_URL=$TEST_DATABASE_URL
alembic upgrade head

uv run pytest tests/test_eval.py tests/test_memory.py -q
```

Without `TEST_DATABASE_URL`, those tests are skipped; pricing/tracker tests still run.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| `connection refused` on 5432 | Postgres not up | `docker compose up -d postgres` and wait for healthy |
| `relation "runs" does not exist` | Migrations not applied | `cd backend && alembic upgrade head` |
| `extension "vector" does not exist` | Plain Postgres image | Use `pgvector/pgvector:pg16` from `docker-compose.yml` |
| `alembic: command not found` | Deps not installed | `uv sync --directory backend --extra dev` |
| Empty `/api/runs` after cutover | No sqlite files or wrong paths | Check `data/eval.db` exists; set `EVAL_DB_PATH` |
| Memory search always empty | No briefs indexed | Run a Daily Brief or `POST /api/memory/reindex` |
| Backend container fails on DB | Schema missing before start | Run Alembic from host (step 3) before `docker compose up backend` |

### Reset Postgres (destructive)

```bash
docker compose down
docker volume rm nba_moa_agents_pg_data   # name may vary: docker volume ls | grep pg
docker compose up -d postgres
cd backend && alembic upgrade head
```

---

## Command cheat sheet

```bash
# Postgres only
docker compose up -d postgres

# Migrations (host, from backend/)
cd backend && DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/nba alembic upgrade head

# SQLite → Postgres backfill
cd backend && uv run python -m scripts.migrate_sqlite_to_postgres

# Full stack
docker compose up --build

# Health
curl -s http://127.0.0.1:8001/api/health
```

---

## What changed vs SQLite

| Before | After |
|--------|-------|
| `data/eval.db` (aiosqlite) | Postgres tables `runs`, `agent_metrics`, `tool_calls` |
| `data/memory.db` + JSON embeddings | Postgres `briefs` / `chunks` + `vector(1536)` + HNSW index |
| Runtime `CREATE TABLE` in repos | Alembic owns schema (`backend/alembic/versions/`) |
| Python loop cosine similarity | pgvector `ORDER BY embedding <=> query` when embeddings exist |

API routes and UI behavior are unchanged; only the persistence layer moved.
