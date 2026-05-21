# LLMOps and evaluation

Every pipeline run is instrumented at runtime, persisted in Postgres, and exposed through the **Evaluation** tab and REST API. The goal is to make **cost, latency, tool behaviour, and source coverage** visible so model routing and failure modes can be tuned from data—not guesswork.

## What is measured

| Signal | Granularity | Used for |
|--------|-------------|----------|
| **Cost (USD)** | Per run, per agent, per model | Model routing, MoA vs Copilot economics |
| **Tokens** | Input / output per agent | Usage spikes, prompt bloat |
| **LLM latency** | Per agent | Slow nodes, model swaps |
| **MCP tool calls** | Per call (agent, tool, success, error, ms) | Failure rate, provider issues |
| **Wall-clock** | Per LangGraph node | Parallelism gains, bottlenecks |
| **Source coverage** | Distinct providers + citation list | Grounding quality, audit trail |
| **Run duration** | End-to-end | SLA-style tracking, p95 in aggregates |

Pricing uses OpenRouter-style estimates per model (`app/eval/pricing.py`). Runs flag `estimated_price` when a model has no known tariff.

## Persistence model

```
RunTracker (in-memory, per request)
        │
        ▼ flush on completion
┌───────────────┐     ┌─────────────────┐     ┌──────────────┐
│     runs      │────▶│  agent_metrics  │     │  tool_calls  │
│  (summary +   │     │  (per agent)    │     │  (per MCP)   │
│   payload)    │     └─────────────────┘     └──────────────┘
└───────────────┘
```

- **`runs`** — mode (`brief` | `query` | `compare`), query, language, timestamps, totals, optional full payload JSON.
- **`agent_metrics`** — one row per agent: model id, token counts, cost, LLM latency, tool counts/failures, wall-clock.
- **`tool_calls`** — each MCP invocation with latency, success flag, and error message when applicable.

Implementation: `backend/app/eval/` (`tracker.py`, `repository.py`, `models.py`).

## How instrumentation works

1. **Request scope** — `use_tracker(mode)` binds a `RunTracker` to the current asyncio task via `ContextVar` (`app/eval/tracker.py`).
2. **Automatic hooks** — `call_llm()` and `mcp_invoke()` in `app/moa/agents/base.py` record tokens, cost, and tool metrics without agent code changes.
3. **LangGraph nodes** — `graph.py` wraps each node to record wall-clock per agent name.
4. **Tool-using agents** — `stats` and NBA Copilot stream via `astream_events`; they call `record_streamed_llm_call` / `record_streamed_tool_call` explicitly.
5. **Citations** — MCP payloads also feed `SourceCitation` rows for the bibliography (same run id).

Nothing is sampled or batched offline: metrics reflect the **actual** execution path of that run.

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/runs?limit=&mode=` | Run history (summaries) |
| `GET /api/runs/{run_id}` | Full run + agent/tool breakdown |
| `GET /api/metrics/summary?last_n=&mode=` | Aggregates: avg cost, p95 duration, tool failure rate, cost by mode |
| WebSocket `/api/ws/run` | Live trace; final frame includes `RunResult.metrics` |

The Evaluation tab consumes these endpoints; no separate analytics service is required for local or demo use.

## Evaluation dashboard (UI)

The **Evaluation** tab provides:

- run history table (filter by mode: Daily Brief, Copilot, Compare);
- summary cards (total runs, avg cost, avg duration, p95, tool failure rate);
- cost-by-mode and cost-per-run charts;
- per-run detail: per-agent latency bars, tool call list, brief output preview;
- for **Compare** runs: split **MoA cost** vs **NBA Copilot cost** on the same prompt.

### Daily Brief run

![Daily Brief — evaluation metrics](images/daily-brief-evaluation.png)

### NBA Copilot run

Copilot runs use the same schema as MoA runs for apples-to-apples comparison across modes.

![NBA Copilot — evaluation](images/copilot-evaluation.png)

### MoA vs NBA Copilot (compare mode)

Same user prompt; two pipelines in parallel. The dashboard stores `moa_cost_usd` (LangGraph MoA brief) and `baseline_cost_usd` (tool-using Copilot with all MCP tools).

![Compare — evaluation](images/compare-evaluation.png)

## What to look at when tuning

| Question | Where to look |
|----------|----------------|
| Is MoA worth the cost vs one Copilot pass? | Compare runs → cost split + side-by-side output quality |
| Which agent dominates spend? | Run detail → per-agent cost / tokens |
| Are tools failing often? | Summary → tool failure rate; run detail → failed `tool_calls` |
| Is latency acceptable? | p95 duration; per-agent wall-clock on brief runs |
| Is the answer grounded? | `distinct_sources`, Sources panel, citation count |

## Live trace vs persisted metrics

| Surface | Role |
|---------|------|
| **WebSocket events** | Real-time agent graph, MCP timeline, chunks (debugging UX) |
| **RunTracker → Postgres** | Durable history, charts, regression comparison across days |

Both share the same run id; the UI can correlate a live session with its row in the Evaluation table after completion.

## Langfuse, Phoenix, OpenTelemetry

This repo uses a **first-party eval store** so the demo is self-contained (no extra SaaS, full control over schema and UI).

The same events map cleanly to standard production stacks:

- **Langfuse** — traces, generations, tool spans, cost;
- **Phoenix / Arize** — eval datasets, drift, quality experiments;
- **OpenTelemetry** — export spans from FastAPI + agent steps into Grafana/Datadog.

A thin adapter on `RunTracker.flush()` (or LangChain callbacks) would duplicate today's signals without changing agent logic. Not wired here by design.

## Code map

| Piece | Path |
|-------|------|
| Collector | `backend/app/eval/tracker.py` |
| Schemas | `backend/app/eval/schemas.py` |
| Postgres repo | `backend/app/eval/repository.py` |
| Pricing | `backend/app/eval/pricing.py` |
| Dashboard UI | `frontend/src/components/EvalDashboard.tsx` |
| API routes | `backend/app/api/routes.py` |
