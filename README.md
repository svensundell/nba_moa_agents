# NBA MoA Agents

> A **Mixture of Agents** system that generates a daily NBA briefing and answers any league question — built with LangGraph, OpenRouter, and the Model Context Protocol.

![python](https://img.shields.io/badge/python-3.11+-blue)
![langgraph](https://img.shields.io/badge/langgraph-1.x-green)
![openrouter](https://img.shields.io/badge/openrouter-deepseek--v4--flash-orange)
![mcp](https://img.shields.io/badge/MCP-3_servers-purple)
![license](https://img.shields.io/badge/license-MIT-lightgrey)

## Why this project?

Most "Mixture of Agents" demos online are abstract, generic chatbots. This one solves a concrete personal problem:

> *I want a daily NBA briefing tailored to my interests, generated automatically every morning, that I can also query interactively to dig deeper.*

Three things make this implementation noteworthy:

1. **Real model diversity** — 8 specialised agents on **3 layers** with role-specific prompts and model slots routed through OpenRouter. Not the same LLM with eight prompts.
2. **Three custom MCP servers** — `nba-stats-mcp` (balldontlie.io), `reddit-mcp` (r/nba JSON) and `espn-mcp` (ESPN NBA RSS). They speak the Model Context Protocol so any MCP client (Claude Desktop, Cursor, our LangGraph agents) can plug into them. **The pipeline is strictly MCP-driven — no HTTP fallbacks**: all external data flows through MCP tools.
3. **Live agent visualisation** — the React frontend uses ReactFlow to show *each agent thinking in real time*, including every MCP tool call, streamed over WebSocket. Perfect for screen-recording the pipeline.

## Architecture

```
                   ┌────── kickoff ──────┐
                   │                     │
   ┌────┬────┬─────┴────┬────────┬───────┴───────────┐
   ▼    ▼    ▼          ▼        ▼                   ▼
 scores news stats   injuries  social         baseline (compare-only)
   L1   L1   L1         L1       L1
    └────┴────┴──────────┴───────┘
                        ▼
                ┌───────┴───────┐
                ▼               ▼
             analyst        narrative
                L2             L2
                └──────┬───────┘
                       ▼
                    editor (L3)
                       ▼
                      END
```

Layers run in parallel inside LangGraph for low-latency end-to-end execution. See [`docs/architecture.md`](docs/architecture.md) for the full deep dive.

### Agent → model → MCP tool lineup

| Agent | Layer | OpenRouter model | MCP tool(s) it calls |
|---|---|---|---|
| scores | proposer | `deepseek/deepseek-v4-flash` | `nba_stats_get_games` |
| news | proposer | `deepseek/deepseek-v4-flash` | `espn_nba_headlines` |
| stats | proposer | `deepseek/deepseek-v4-flash` | `nba_stats_search_players`, `nba_stats_team_recent_games` |
| injuries | proposer | `deepseek/deepseek-v4-flash` | `espn_nba_injury_headlines` |
| social | proposer | `deepseek/deepseek-v4-flash` | `reddit_top_posts` / `reddit_search_posts` |
| analyst | refiner | `deepseek/deepseek-v4-flash` | (no tool — synthesises proposals) |
| narrative | refiner | `deepseek/deepseek-v4-flash` | (no tool — synthesises proposals) |
| editor | aggregator | `deepseek/deepseek-v4-flash` | (no tool — composes final brief) |

### MCP servers (all custom, all in this repo)

| Server | Path | Wraps | Tools |
|---|---|---|---|
| **`nba_stats`** | `mcp_servers/nba_stats/server.py` | balldontlie.io v1 | `get_games`, `search_players`, `list_teams`, `team_recent_games` |
| **`reddit`** | `mcp_servers/reddit/server.py` | Public Reddit JSON | `top_posts`, `hot_posts`, `search_posts` |
| **`espn`** | `mcp_servers/espn/server.py` | ESPN NBA RSS | `nba_headlines`, `nba_injury_headlines` |

## Three demo modes

| Mode | Description |
|---|---|
| **Daily Brief** | One click → a structured NBA briefing for last night |
| **Ask Anything** | Free-form NBA questions answered by a LangChain agent with access to all MCP tools |
| **MoA vs Single LLM** | Split-screen comparison showing the value the MoA pattern adds |

## Quick start

### Prerequisites

- Python 3.11+
- Node.js 20+
- An [OpenRouter API key](https://openrouter.ai/)

Set `BALLDONTLIE_API_KEY` in `.env` (required by the NBA MCP server).

### Run locally

```bash
# 1. Configure
cp .env.example .env
# fill in OPENROUTER_API_KEY (mandatory), BRAVE_API_KEY (optional)

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

```bash
cp .env.example .env
docker compose up
```

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
│   │   ├── main.py              FastAPI entrypoint
│   │   ├── api/                 REST + WebSocket routes
│   │   ├── moa/
│   │   │   ├── graph.py         LangGraph StateGraph
│   │   │   ├── state.py         Shared state schema
│   │   │   ├── llm.py           OpenRouter model registry
│   │   │   └── agents/          Per-agent logic + prompts
│   │   ├── mcp/                 MCP client manager
│   │   └── core/                Config & logging
│   ├── scripts/demo.py          CLI demo runner
│   └── tests/
├── mcp_servers/
│   └── nba_stats/               Custom MCP server (balldontlie wrapper)
├── frontend/                    React + Vite + ReactFlow
└── docs/architecture.md
```

## Plug the custom MCP servers into Claude Desktop / Cursor

The three MCP servers in `mcp_servers/` are reusable on their own — drop them into any MCP-aware client:

- [`mcp_servers/nba_stats/README.md`](mcp_servers/nba_stats/README.md) — NBA games, players, teams (free-plan-safe)
- [`mcp_servers/reddit/README.md`](mcp_servers/reddit/README.md) — r/nba (or any subreddit) JSON wrapper
- [`mcp_servers/espn/README.md`](mcp_servers/espn/README.md) — ESPN NBA RSS feed

## Roadmap

- [x] Project scaffolding
- [x] LangGraph MoA pipeline
- [x] 8 specialised NBA agents
- [x] Custom NBA MCP server
- [x] FastAPI + WebSocket streaming
- [x] React frontend with live agent flow
- [x] MoA vs Single LLM comparison
- [x] CLI demo runner
- [ ] Scheduled daily briefing (cron + email/Slack)
- [ ] Brief history & favourites
- [ ] Deployment guide (Fly.io / Render)

## License

MIT
