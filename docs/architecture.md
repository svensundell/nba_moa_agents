# Architecture

## Goals

1. **Real Mixture-of-Agents** — multiple *different* models reason in parallel,
   then a refinement layer reasons over their outputs, then an aggregator
   composes the final answer. This is the topology of the original [Together
   AI MoA paper](https://arxiv.org/abs/2406.04692), specialised for NBA
   content.
2. **MCP-native** — the system both *consumes* MCP servers (Brave Search,
   Fetch, our own NBA stats server) and *exposes* a custom MCP server that
   any other client (Claude Desktop, Cursor) can plug into.
3. **Demoable** — anyone can clone, set a Groq API key, run `docker compose
   up`, and get a working live demo on `localhost:5173`.

## Pipeline

```
                   ┌────── kickoff ──────┐
                   │                     │
   ┌────┬────┬─────┴────┬────────┬───────┴───────────┐
   ▼    ▼    ▼          ▼        ▼                   ▼
 scores news stats   injuries  social         baseline (compare-only)
  L1   L1    L1         L1       L1                  ─
   └────┴───┬┴──────────┴────────┘
            ▼
      ┌─────┴──────┐
      ▼            ▼
    analyst     narrative
      L2           L2
      └─────┬──────┘
            ▼
          editor (L3)
            ▼
           END
```

LangGraph executes nodes sharing an incoming edge in **parallel**, so the
whole layer-1 fans out concurrently. Layer-2 waits for the layer-1 join, then
fans out again. The editor finally synthesises everything.

## Model lineup

The point of MoA is *model diversity*. Here, every node intentionally uses a
different family:

| Agent     | Model (Groq)                         | Why |
|-----------|---------------------------------------|---|
| scores    | `llama-3.1-8b-instant`                | Cheap, structured-output reliable |
| news      | `llama-3.3-70b-versatile`             | Strong reasoning over headlines |
| stats     | `llama-3.3-70b-versatile`             | Numerical reasoning + thinking trace |
| injuries  | `llama-3.1-8b-instant`                | Filter+format task is small |
| social    | `llama-3.1-8b-instant`                | Sentiment-friendly, terse outputs |
| analyst   | `llama-3.3-70b-versatile`             | Cross-checking, broad context |
| narrative | `llama-3.3-70b-versatile`             | Storytelling + creative arcs |
| editor    | `llama-3.3-70b-versatile`             | Best long-form generator |
| baseline  | `llama-3.3-70b-versatile`             | Same model the editor uses, alone |

## State management

The graph state lives in `app/moa/state.py`:

- `proposals` (list, accumulated): one `AgentProposal` per layer-1 node
- `refinements` (list, accumulated): one `AgentRefinement` per layer-2 node
- `final_brief` / `single_llm_answer` (string, last write wins)
- `events` (list, accumulated): everything that goes to the WebSocket

Channels using `operator.add` allow parallel writes from sibling nodes
without conflict.

## MCP integration

The pipeline is **strictly MCP-driven**: every external data fetch goes
through a tool call on one of three custom MCP servers. There are *no* HTTP
fallbacks — if MCP is down, the corresponding agent emits an explicit error
event and the pipeline degrades gracefully (the editor still produces a
brief from whatever proposals succeeded).

| Server | Path | Wrapped source | Tools |
|---|---|---|---|
| `nba_stats` | `mcp_servers/nba_stats/server.py` | balldontlie.io v1 | 6 tools |
| `reddit` | `mcp_servers/reddit/server.py` | Public Reddit JSON | 3 tools |
| `espn` | `mcp_servers/espn/server.py` | ESPN NBA RSS | 2 tools |

All three are launched as **stdio subprocesses** by
`langchain_mcp_adapters.MultiServerMCPClient` at FastAPI startup (see
`backend/app/main.py` lifespan). Tools are loaded with `tool_name_prefix=True`
so each tool surfaces as `<server>_<tool>` (e.g. `nba_stats_get_games`,
`reddit_top_posts`, `espn_nba_injury_headlines`).

### Why three custom MCP servers?

Each server isolates one domain and stays small enough to be reusable on its
own:

- ``nba_stats`` is the showcase wrapper around a structured stats API.
- ``reddit`` is a generic subreddit wrapper — the same server works for
  ``r/nba``, ``r/nfl``, ``r/fantasybball`` etc.
- ``espn`` is a thin RSS adapter and is the easiest one to extend with new
  feeds (NFL, NHL, soccer, ...).

A user can drop *any one* of them into Claude Desktop or Cursor without
running this whole project — see the README of each server.

### Lifecycle

1. ``MCPRegistry.initialize()`` is called by FastAPI's lifespan. It builds
   the multi-server config, spawns each Python subprocess, lists their
   tools, and caches them in a process-wide ``dict[str, BaseTool]``.
2. Agents call ``mcp_invoke(agent, tool_name, args)`` (in
   ``app/moa/agents/base.py``) which:
   - looks up the tool by name (raises ``MCPToolMissing`` if absent),
   - invokes the underlying coroutine to get the raw
     ``(content, artifact)`` tuple,
   - extracts text content and emits a structured ``"tool"`` event for the
     UI trace.
3. ``MCPRegistry.shutdown()`` runs on FastAPI shutdown (idempotent).

If ``initialize()`` fails the FastAPI startup aborts — there is no
"degraded MCP-less mode" by design.

## Streaming

The WebSocket endpoint `/api/ws/run` consumes LangGraph's `astream(...,
stream_mode="updates")` and forwards every node's `events` list to the
frontend in real time. The React UI uses these events to highlight nodes in
the ReactFlow graph, producing the live "watch agents thinking" effect.

## Comparing modes

The `compare` mode runs the **full MoA** alongside a **single-model
baseline** (`llama-3.3-70b-versatile` answering directly). Both run in
parallel inside the same graph and the UI shows them side by side. This is
the highest-leverage demo: it shows when MoA actually adds value vs. just
costing more tokens.
