# NBA MoA Agents

> A **Mixture of Agents** system that produces a structured daily NBA briefing and includes **NBA Copilot** — a multi-turn, MCP-powered research chat — built with LangGraph, OpenRouter and the Model Context Protocol.

![python](https://img.shields.io/badge/python-3.11+-blue)
![langgraph](https://img.shields.io/badge/langgraph-0.2-green)
![openrouter](https://img.shields.io/badge/openrouter-5_model_families-orange)
![mcp](https://img.shields.io/badge/MCP-3_servers_·_11_tools-purple)
![license](https://img.shields.io/badge/license-MIT-lightgrey)

## Why this project?

Most "Mixture of Agents" demos online are abstract chat playgrounds. This one solves a concrete personal problem:

> *I want a structured NBA briefing for last night, generated automatically every morning, and **NBA Copilot** to dig deeper interactively.*

Three things make this implementation noteworthy:

1. **Real model diversity over OpenRouter** — 9 specialised agents on 3 layers, routed through **5 different model families** (DeepSeek, Google Gemini, Qwen, Mistral). Different roles, different brains — not the same LLM with eight prompts.
2. **Three custom MCP servers, 11 tools total** — `nba-stats-mcp` (balldontlie.io), `reddit-mcp` (r/nba JSON) and `espn-mcp` (ESPN RSS + ESPN site API for boxscores). They speak the Model Context Protocol so any MCP client (Claude Desktop, Cursor, our LangGraph agents) can plug into them. **The pipeline is strictly MCP-driven — no HTTP fallbacks.**
3. **Hybrid orchestration** — the `brief` mode runs a *deterministic* LangGraph MoA pipeline (perfect for a daily recap). **NBA Copilot** (`query` mode) runs a *dynamic* LangChain `create_agent` with the full MCP toolset, supports multi-turn chat history, and streams each tool decision over WebSocket so the frontend renders a live MCP tool timeline.

## Architecture

```
                   ┌──────── kickoff ────────┐
                   │                         │
   ┌────┬────┬─────┴────┬──────────┬─────────┴──────────┐
   ▼    ▼    ▼          ▼          ▼                    ▼
 scores news stats   injuries   social         baseline (compare-only)
   L1   L1  L1*        L1         L1                    └─ END
    └────┴───┬┴──────────┴──────────┘
             ▼
       ┌─────┴─────┐
       ▼           ▼
    analyst    narrative
       L2         L2
       └─────┬─────┘
             ▼
          editor (L3)
             ▼
            END
```

`L1*` = the `stats` proposer is a **tool-using LangChain agent**: it autonomously decides which ESPN/balldontlie tools to call to get exact statlines.

LangGraph executes nodes that share an incoming edge in **parallel**, so layer-1 fans out concurrently. Layer-2 waits for the layer-1 join, then fans out again. The editor finally synthesises everything. See [`docs/architecture.md`](docs/architecture.md) for the full deep dive.

### Agent → model → MCP tool lineup

| Agent       | Layer       | OpenRouter model                              | MCP tool(s) it calls |
|-------------|-------------|-----------------------------------------------|----------------------|
| `scores`    | proposer    | `google/gemini-2.5-flash`                     | `nba_stats_get_games` (yesterday + today) |
| `news`      | proposer    | `google/gemini-2.5-flash`                     | `espn_nba_headlines` |
| `stats`     | proposer\*  | `qwen/qwen3.6-35b-a3b`                        | `espn_nba_scoreboard`, `espn_nba_boxscore`, `espn_nba_headlines`, `nba_stats_get_games`, `nba_stats_search_players` |
| `injuries`  | proposer    | `google/gemini-2.5-flash`                     | `espn_nba_injury_headlines` |
| `social`    | proposer    | `mistralai/mistral-small-24b-instruct-2501`   | `reddit_top_posts` / `reddit_search_posts` |
| `analyst`   | refiner     | `qwen/qwen3.6-35b-a3b`                        | (no tool — fact-checks the proposals) |
| `narrative` | refiner     | `deepseek/deepseek-chat-v3.1`                 | (no tool — finds storylines) |
| `editor`    | aggregator  | `deepseek/deepseek-chat-v3.1`                 | (no tool — composes the final brief) |
| `baseline`  | compare-only| `deepseek/deepseek-chat-v3.1`                 | (no tool — single-LLM control) |
| `nba_copilot` | NBA Copilot | `deepseek/deepseek-v4-pro`      | **all 11 MCP tools** (autonomous tool selection) |

\* `stats` is a tool-using agent: it plans up to ~6 tool calls per run to ground its bullets in **exact statlines** lifted from ESPN's boxscore data.

### MCP servers (all custom, all in this repo)

| Server          | Path                              | Wraps               | Tools |
|-----------------|-----------------------------------|---------------------|-------|
| **`nba_stats`** | `mcp_servers/nba_stats/server.py` | balldontlie.io v1   | `get_games`, `search_players`, `list_teams`, `team_recent_games` |
| **`reddit`**    | `mcp_servers/reddit/server.py`    | Public Reddit JSON  | `top_posts`, `hot_posts`, `search_posts` |
| **`espn`**      | `mcp_servers/espn/server.py`      | ESPN NBA RSS + site API | `nba_headlines`, `nba_injury_headlines`, `nba_scoreboard`, `nba_boxscore` |

All three are launched as **stdio subprocesses** by `langchain_mcp_adapters.MultiServerMCPClient` at FastAPI startup, with `tool_name_prefix=True` so each tool surfaces as `<server>_<tool>` (e.g. `nba_stats_get_games`, `espn_nba_boxscore`).

## Four demo modes

| Mode                  | Orchestration          | What it does |
|-----------------------|------------------------|--------------|
| **Daily Brief**       | Deterministic LangGraph MoA | One click → a structured 7-section briefing for last night (Quick Hits / Box Score Recap / Standout Statlines / Trades & News / Injuries Watch / Storyline / Fan Pulse). |
| **NBA Copilot** | Dynamic LangChain `create_agent` | Multi-turn NBA chat with tool-using reasoning. The agent decides which MCP tools to call from conversation context, and tool decisions stream live to the UI. |
| **MoA vs Single LLM** | LangGraph MoA + parallel single-LLM baseline | Side-by-side comparison showing where the MoA pattern adds value (and where it doesn't). |
| **Evaluation Dashboard** | Persisted run metrics (SQLite) | Cost (USD), token usage, per-agent latency, MCP tool failure rate and source coverage for every run. MoA vs single-LLM cost ratio is charted for `compare` runs. |

### Evaluation & observability

Every pipeline invocation is observed end-to-end and persisted to
`data/eval.db` (SQLite, auto-created at startup). A `RunTracker` is
bound to each request via a `ContextVar`, so every `call_llm` and every
MCP `mcp_invoke` records:

- LLM tokens (input / output) and (priced) cost per `(agent, model)`
- LLM and MCP tool latency
- MCP success / failure (powering a tool failure-rate gauge)
- Distinct sources cited across the run
- Wall-clock time per LangGraph node

Three endpoints expose the history:

- `GET /api/runs?limit=…&mode=…` — recent runs (summary).
- `GET /api/runs/{id}` — full payload including the per-agent breakdown.
- `GET /api/metrics/summary?last_n=…` — aggregates (avg cost, p95 latency,
  tool failure rate, MoA vs baseline cost) used by the dashboard.

The "Evaluation" tab in the frontend renders all of this, with a run
history table, cost-per-run / cost-per-mode bar charts and an inline
per-agent latency chart for any selected run.

## Quick start

### Prerequisites

- Python 3.11+ and Node.js 20+ (local dev), **or** Docker + Docker Compose v2 (containerised run)
- An [OpenRouter API key](https://openrouter.ai/) (one key, all the models the agents use)
- Optional: a [balldontlie API key](https://www.balldontlie.io/) for higher-quota NBA stats requests

### Run locally

```bash
# 1. Configure
cp .env.example .env
# fill in OPENROUTER_API_KEY (required) and BALLDONTLIE_API_KEY (optional)

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# 3. Frontend (in a second terminal)
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

### Run with Docker

Requires [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2.

```bash
# 1. Configure (OPENROUTER_API_KEY is required)
cp .env.example .env

# 2. Build and start backend + frontend
docker compose up --build
```

| URL | Purpose |
|-----|---------|
| <http://localhost:5173> | Web UI (nginx serves the React build and proxies `/api` to the backend) |
| <http://127.0.0.1:8001/docs> | FastAPI Swagger (direct backend access) |
| <http://127.0.0.1:8001/api/health> | Health check |

The frontend container waits until the backend healthcheck passes (MCP servers
can take up to ~90s on first boot). Run metrics are stored in a Docker volume
(`eval_data` → `/app/data/eval.db` inside the backend container).

```bash
# Detached mode
docker compose up --build -d

# Stop and remove containers
docker compose down
```

**Port notes**

- The UI is published on **5173** (same as local `npm run dev`).
- The API is exposed on **8001** (not 8000) so you can keep a local
  `uvicorn` on `:8000` while Docker is running.
- Prefer **http://127.0.0.1:5173** if another process already owns port 8000
  on `localhost` via IPv6 (common with an old Docker container on macOS).

### Run from the CLI (no frontend)

```bash
cd backend && source .venv/bin/activate
python -m scripts.demo brief
python -m scripts.demo query "How is Luka Doncic playing this season?"
python -m scripts.demo compare "What should the Lakers do at the deadline?"
```

## Project structure

```
nba_moa_agents/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI entrypoint (MCP lifespan)
│   │   ├── api/                 REST + WebSocket routes (/brief, /query, /compare, /ws/run)
│   │   ├── moa/
│   │   │   ├── graph.py         LangGraph StateGraph for brief & compare modes
│   │   │   ├── state.py         Shared state schema + AgentEvent
│   │   │   ├── llm.py           OpenRouter model registry + agent → model mapping
│   │   │   ├── open_query.py    Tool-using LangChain agent for NBA Copilot
│   │   │   └── agents/          Per-agent logic + prompts (proposers / refiners / editor)
│   │   ├── mcp/                 MCPRegistry: launches & caches the 3 MCP servers
│   │   └── core/                Config & logging
│   ├── scripts/demo.py          CLI demo runner
│   └── tests/                   Smoke tests (no LLM calls)
├── mcp_servers/
│   ├── nba_stats/               Custom MCP server (balldontlie wrapper)
│   ├── reddit/                  Custom MCP server (public Reddit JSON wrapper)
│   └── espn/                    Custom MCP server (ESPN RSS + site API wrapper)
├── frontend/                    React 18 + Vite + TypeScript + Tailwind + ReactFlow
│   ├── src/App.tsx              Mode tabs · agent graph · MCP tool timeline · live trace
│   └── src/api.ts               REST + WebSocket client
├── docker-compose.yml
└── docs/architecture.md
```

## Plug the custom MCP servers into Claude Desktop / Cursor

The three MCP servers in `mcp_servers/` are reusable on their own — drop them into any MCP-aware client:

- [`mcp_servers/nba_stats/README.md`](mcp_servers/nba_stats/README.md) — NBA games, players, teams (free-plan-safe)
- [`mcp_servers/reddit/README.md`](mcp_servers/reddit/README.md) — r/nba (or any subreddit) JSON wrapper
- [`mcp_servers/espn/README.md`](mcp_servers/espn/README.md) — ESPN NBA RSS feed + scoreboard + per-player boxscores

## Roadmap

- [x] Project scaffolding
- [x] LangGraph MoA pipeline
- [x] 9 specialised NBA agents on 5 model families
- [x] Three custom MCP servers (nba_stats, reddit, espn)
- [x] Strictly MCP-driven data layer (no HTTP fallbacks)
- [x] Hybrid orchestration: deterministic MoA for `brief`, dynamic multi-turn tool-using agent for NBA Copilot
- [x] FastAPI + WebSocket streaming with live MCP tool timeline
- [x] React frontend with ReactFlow agent graph + tool timeline
- [x] MoA vs Single LLM comparison
- [x] CLI demo runner
- [x] Evaluation dashboard: cost / latency / tool-failure / source-coverage per run, persisted to SQLite
- [ ] Source citations + trace-back to the tool output that produced each line
- [ ] Scheduled daily briefing (cron + email/Slack)
- [ ] Brief history & favourites
- [ ] Deployment guide (Fly.io / Render)

## License

MIT
