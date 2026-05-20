# Case Study — NBA MoA Agents

## One-line summary

Built an agentic NBA analysis system combining a deterministic Mixture-of-Agents pipeline for structured daily briefings and a dynamic tool-using copilot for open research questions, with end-to-end observability, source traceability, and temporal RAG memory.

## Context and objective

Most LLM demos stop at "it answers."  
The objective here was different: ship a system that behaves like a real product surface:

- reliable output shape for a repeatable daily workflow;
- grounded answers from explicit data tools;
- measurable cost/latency/failure signals;
- architecture that another engineer can run and extend quickly.

The product problem is intentionally concrete:

- **Daily Brief**: "What happened in the NBA last night?"
- **NBA Copilot**: "Help me investigate a storyline with live data + past context."

## What I built

### 1) Two orchestration patterns in one product

- **Deterministic LangGraph MoA** for `brief`:
  - parallel specialist proposers (`scores`, `news`, `stats`, `injuries`, `social`);
  - refinement layer (`analyst`, `narrative`);
  - constrained final editor with a fixed 7-section structure.
- **Dynamic tool-using agent** for `query`:
  - multi-turn copilot based on LangChain `create_agent`;
  - autonomous MCP tool selection depending on user intent.

This split is deliberate: repeatable outputs for recurring briefs, adaptive planning for open-ended questions.

### 2) MCP-native data layer

Three custom MCP servers expose 11 tools:

- `nba_stats` (balldontlie),
- `espn` (news/scoreboard/boxscore),
- `reddit` (community sentiment).

Agents never call external providers directly. All data access passes through MCP tool boundaries for auditable execution and reusable integrations across clients (Cursor, Claude Desktop, etc.).

### 3) Observability and evaluation baked into runtime

Each run persists metrics in Postgres:

- total/per-agent cost and tokens;
- LLM and tool latency;
- tool-call count and failures;
- source coverage and per-node wall-clock time.

The frontend evaluation surface compares modes over time (including side-by-side `compare` runs).

### 4) Source traceability and memory (RAG)

- Every MCP call is transformed into structured source citations (provider, tool, timestamp, URL when available, excerpt).
- Daily Brief includes inline citation references and a Sources panel.
- Historical briefs are chunked, embedded, and indexed with `pgvector` for temporal retrieval by the copilot.

## Architecture decisions and trade-offs

### Why MoA for the Daily Brief?

The brief has a stable shape and quality bar. A deterministic graph with specialist nodes yields more consistent structure and easier regression analysis than one-shot prompting.

### Why a dynamic tool-using Copilot?

User questions vary too much for a fixed DAG. Dynamic planning handles different intents (injury context, stat validation, sentiment check) while still staying grounded via tools.

### Why MCP-only instead of ad hoc HTTP calls?

MCP gives explicit interfaces and better portability. It also makes failures visible: when a provider breaks, the system emits tool errors rather than silently fabricating missing data.

### Why custom evaluation storage instead of only external LLMOps?

For this project, a local-first Postgres model gives full control over run-level analytics and UI integration.  
In client work, the same signals can be mirrored to Langfuse/Phoenix/OpenTelemetry stacks.

## Reliability and quality engineering

- FastAPI backend with typed schemas (Pydantic v2) and WebSocket streaming.
- SQLAlchemy async + Alembic migrations for persistence lifecycle.
- CI pipeline for lint/typecheck/tests/frontend build.
- Makefile for reproducible local workflows (`dev`, `test`, `lint`, `typecheck`, `migrate`).
- Tests cover graph structure, repositories, and MCP server helper behavior.

## Results and deliverables

The project delivers:

- a working multi-mode application (brief, copilot, compare, evaluation);
- visible execution traces and source provenance;
- measurable performance/cost/failure data for iteration;
- production-leaning foundations (containerized stack, migrations, CI, tests).

## Skills demonstrated

- **Agent architecture**: LangGraph + dynamic tool-using agents, state design, orchestration boundaries.
- **LLM integration**: model routing, tool grounding, prompt constraints, output shaping.
- **RAG/memory**: chunking, embeddings, vector retrieval, temporal context reuse.
- **LLMOps mindset**: runtime instrumentation, comparative evaluation, failure visibility.
- **Backend engineering**: FastAPI, async Python, Postgres/pgvector, migration discipline.
- **Product engineering**: frontend traceability UX, live observability surfaces, explainability.

## What is intentionally not implemented yet

- Scheduled and automatically distributed Daily Brief workflow (cron/email/Slack).
- Controlled public deployment tier for demo traffic and quota protection.

Those are productization choices, not architectural blockers.

