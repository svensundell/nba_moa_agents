# Testing and CI

Automated checks run on every push and pull request to `main` / `master`. The pipeline is designed to catch regressions in **graph wiring**, **persistence**, **MCP helpers**, and **frontend build** without calling live LLMs or spawning MCP subprocesses in CI.

[![CI](https://github.com/svensundell/nba_moa_agents/actions/workflows/ci.yml/badge.svg)](https://github.com/svensundell/nba_moa_agents/actions/workflows/ci.yml)

## CI pipeline (GitHub Actions)

| Job | Steps |
|-----|--------|
| **backend** | Ruff lint + format check → mypy `app/` → pytest (smoke) → pytest (Postgres integration with `pgvector`) |
| **frontend** | `npm ci` → `npm run build` (TypeScript + Vite production bundle) |

Postgres service: `pgvector/pgvector:pg16`, database `nba_test`, same extension and schema as production (via SQLAlchemy `Base.metadata` in tests).

Workflow file: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

## Test layout

| File | Scope | Network / LLM |
|------|--------|----------------|
| `test_smoke.py` | Imports, LangGraph compile, expected nodes, MCP server paths on disk | No |
| `test_graph_workflow.py` | `initial_state` per mode, graph topology | No |
| `test_mcp_servers.py` | Pure helpers in ESPN/Reddit MCP servers (injury filter, score shaping, post trim) | No |
| `test_citations.py` | `SourceCitation` formatting and URL extraction | No |
| `test_eval.py` | `RunTracker`, pricing, repository CRUD + aggregates | Postgres only |
| `test_memory.py` | Chunking, embeddings interface, pgvector search + keyword fallback | Postgres only |

Integration tests (`test_eval`, `test_memory`) **skip** when `TEST_DATABASE_URL` is unset; CI always sets it.

## What is covered

- **LangGraph structure** — required nodes exist; compare mode includes `baseline`.
- **Agent ↔ model registry** — every agent maps to a known OpenRouter logical model.
- **MCP data shaping** — response normalisation logic without hitting ESPN/Reddit APIs.
- **Eval persistence** — run insert, metrics rollups, dashboard summary fields.
- **Memory** — chunk upsert, vector search path, repository contracts.
- **Citations** — numbered index and provider metadata for the editor/UI.

## What is intentionally not in CI

| Gap | Reason |
|-----|--------|
| Live LLM calls | Cost, flakiness, API keys in CI secrets |
| MCP subprocess e2e | Slow boot (~90s), environment-dependent |
| Golden prompt regression | No frozen dataset yet; eval dashboard supports manual comparison |
| Frontend component tests | Build + typecheck via `tsc`/`vite build` is the current gate |

For manual validation: run the app locally (`make dev`) and enter your OpenRouter key in the Access screen, or `export OPENROUTER_API_KEY=…` then `python -m scripts.demo brief`.

## Run locally

```bash
# Unit + smoke (no Postgres required for most tests)
make test-backend
# or
cd backend && uv run pytest -q

# Lint + types (same as CI)
make lint
make typecheck

# Postgres integration (Docker)
docker compose up -d postgres
createdb -h 127.0.0.1 -U postgres nba_test 2>/dev/null || true
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/nba_test make test-integration

# Full gate (backend + frontend build)
make test
```

## Adding tests

- **New MCP helper** — add cases to `test_mcp_servers.py` (load module via `importlib`, no subprocess).
- **New graph node** — update `test_smoke.py` / `test_graph_workflow.py` expected node set.
- **New persistence** — extend `test_eval.py` or `test_memory.py` with the `pg_session_factory` fixture from `conftest.py`.

Keep tests deterministic: no wall-clock sleeps, no external HTTP unless explicitly marked and skipped in CI.
