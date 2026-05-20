# Architecture

## Goals

1. **Real Mixture-of-Agents** — multiple *different* models reason in parallel,
   then a refinement layer reasons over their outputs, then an aggregator
   composes the final answer. This is the topology of the original
   [Together AI MoA paper](https://arxiv.org/abs/2406.04692), specialised for
   NBA content.
2. **MCP-native, MCP-only** — every external interaction goes through one of
   the three custom MCP servers shipped with the repo (`nba_stats`, `reddit`,
   `espn`). There are *no* HTTP fallbacks: agents that can't reach their tool
   emit an explicit error event and the pipeline degrades gracefully.
3. **Demoable** — anyone can clone, set an OpenRouter API key, run
   `docker compose up`, and watch the agents work live on `localhost:5173`.

## Pipeline

```
                   ┌──────── kickoff (start event) ────────┐
                   │                                       │
   ┌────┬────┬─────┴────┬──────────┬─────────┬─────────────┤
   ▼    ▼    ▼          ▼          ▼         ▼             │
 scores news stats   injuries   social   baseline (compare-only)
  L1   L1   L1*        L1         L1         └──── END ────┘
   └────┴───┬┴──────────┴──────────┘
            ▼ (barrier: wait for all proposers)
      ┌─────┴──────┐
      ▼            ▼
    analyst     narrative
      L2           L2
      └─────┬──────┘
            ▼ (barrier: wait for both refiners)
          editor (L3)
            ▼
           END
```

LangGraph executes nodes that share an incoming edge in **parallel**, so the
whole layer-1 fans out concurrently. Layer-2 waits for the layer-1 join, then
fans out again. The editor finally synthesises everything.

`L1*` = the `stats` proposer is itself a tool-using LangChain agent (see
"Three agent shapes" below). The other layer-1 agents are direct-tool-call
proposers.

## Three agent shapes

This is the most useful mental model for the codebase. We have *three* very
different agent shapes, and the choice is intentional per role:

1. **Direct-tool-call proposers** — `scores`, `news`, `injuries`, `social`.
   Python code calls one (or two) MCP tools via `mcp_invoke`, formats the
   response into snippets, then asks the LLM to summarise. Predictable
   latency, predictable cost. Lives in
   `app/moa/agents/proposers/{scores,news,injuries,social}.py`.

2. **Tool-using proposer** — `stats`. Uses
   `langchain.agents.create_agent` with a curated subset of MCP tools
   (`espn_nba_scoreboard`, `espn_nba_boxscore`, `espn_nba_headlines`,
   `nba_stats_get_games`, `nba_stats_search_players`) and lets the LLM plan
   the tool calls (cap: 6). The LLM is instructed to always pull at least one
   `nba_boxscore` to ground its bullets in **exact statlines** lifted from
   ESPN. Lives in `app/moa/agents/proposers/stats.py`.

3. **Synthesisers** — `analyst` (factual cross-check) and `narrative` (story
   angle). Pure LLM calls, no tools, consume the layer-1 proposals. Lives in
   `app/moa/agents/refiners/`.

The aggregator (`editor`) is the final synthesiser: pure LLM, no tools, but
with a strict 7-section markdown template (see "Brief output structure"
below). Lives in `app/moa/agents/editor.py`.

The `baseline` node is special: a single-LLM control that runs only when
`mode=="compare"` and reaches `END` directly without going through the
refiners or the editor.

**NBA Copilot** (`query` mode) is its own beast — it doesn't go through this
graph at all. See "Hybrid orchestration".

## Model lineup

The point of MoA is *model diversity*. We route everything through
**OpenRouter** with `langchain_openai.ChatOpenAI` so a single API key
multiplexes 5 different model families:

| Logical slot | OpenRouter model id                            | Used by |
|--------------|------------------------------------------------|---------|
| `fast`       | `google/gemini-2.5-flash`                      | `scores`, `news`, `injuries` |
| `reasoner`   | `qwen/qwen3.6-35b-a3b`                         | `stats`, `analyst` |
| `synthesis`  | `deepseek/deepseek-chat-v3.1`                  | `narrative` |
| `balanced`   | `deepseek/deepseek-chat-v3.1`                  | `editor`, `baseline` |
| `budget`     | `mistralai/mistral-small-24b-instruct-2501`    | `social` |
| `open_query` | `deepseek/deepseek-v4-pro`                     | NBA Copilot tool-using agent |

The agent → slot mapping is the single source of truth and lives in
`AGENT_MODELS` in `app/moa/llm.py`. Tweak that dict to recompose the MoA
without touching agent code.

## State management

The graph state lives in `app/moa/state.py`:

- `proposals` (list, accumulated): one `AgentProposal` per layer-1 node.
- `refinements` (list, accumulated): one `AgentRefinement` per layer-2 node.
- `final_brief` / `single_llm_answer` (string, last write wins).
- `events` (list, accumulated): everything that goes to the WebSocket trace.
  Tool events may carry optional citation metadata (`citation_id`,
  `provider`, `tool`, `retrieved_at`, `source_url`) for the live MCP timeline.

Channels using `operator.add` allow parallel writes from sibling nodes
without conflict.

## MCP integration

The pipeline is **strictly MCP-driven**: every external data fetch goes
through a tool call on one of three custom MCP servers. There are *no* HTTP
fallbacks — if MCP is down, the offending agent emits an explicit error
event and the pipeline degrades gracefully (the editor still produces a
brief from whatever proposals succeeded).

| Server     | Path                              | Wrapped source            | Tools |
|------------|-----------------------------------|---------------------------|-------|
| `nba_stats`| `mcp_servers/nba_stats/server.py` | balldontlie.io v1         | 4 tools (`get_games`, `search_players`, `list_teams`, `team_recent_games`) |
| `reddit`   | `mcp_servers/reddit/server.py`    | Public Reddit JSON        | 3 tools (`top_posts`, `hot_posts`, `search_posts`) |
| `espn`     | `mcp_servers/espn/server.py`      | ESPN NBA RSS + site API   | 4 tools (`nba_headlines`, `nba_injury_headlines`, `nba_scoreboard`, `nba_boxscore`) |

That's **11 MCP tools total** loaded into the registry as
`<server>_<tool>` (e.g. `espn_nba_boxscore`).

All three servers are launched as **stdio subprocesses** by
`langchain_mcp_adapters.MultiServerMCPClient` at FastAPI startup (see
`backend/app/main.py` lifespan and `app/mcp/client.py`). Tools are loaded
with `tool_name_prefix=True` so each tool surfaces with its server prefix.

### Why three custom MCP servers?

Each server isolates one domain and stays small enough to be reusable on its
own:

- `nba_stats` is the showcase wrapper around a structured stats API.
- `reddit` is a generic subreddit wrapper — the same server works for
  `r/nba`, `r/nfl`, `r/fantasybball` etc.
- `espn` is a thin RSS + scoreboard + boxscore adapter. The boxscore tool
  is what unlocks "exact statline" reporting in the daily brief.

A user can drop *any one* of them into Claude Desktop or Cursor without
running this whole project — see the README of each server.

### Lifecycle

1. `MCPRegistry.initialize()` is called by FastAPI's lifespan. It builds
   the multi-server config, spawns each Python subprocess, lists their
   tools, and caches them in a process-wide `dict[str, BaseTool]`.
2. Direct-tool-call agents call `mcp_invoke(agent, tool_name, args)` (in
   `app/moa/agents/base.py`) which:
   - looks up the tool by name (raises `MCPToolMissing` if absent),
   - invokes the underlying coroutine to get the raw `(content, artifact)`
     tuple from `langchain-mcp-adapters`,
   - extracts text content and emits a structured `"tool"` event for the
     UI trace (with `citation_id`, `provider`, `retrieved_at`, `source_url`
     when a `RunTracker` is active — see "Source traceability").
   - calls `RunTracker.record_mcp_citation()` so each successful tool
     invocation becomes a numbered `SourceCitation` in the run bibliography.
3. Tool-using agents (`stats`, `nba_copilot`) bypass `mcp_invoke` and pass
   the LangChain tool objects straight to `create_agent(tools=...)`. Tool
   call events are reconstructed from `astream_events("v2")` and re-emitted
   as `AgentEvent`s with `type="tool"` for the UI.
4. `MCPRegistry.shutdown()` runs on FastAPI shutdown (idempotent).

If `initialize()` fails, FastAPI startup aborts — there is no
"degraded MCP-less mode" by design.

## Streaming

The WebSocket endpoint `/api/ws/run` is mode-aware:

- **`brief` / `compare`** — consumes LangGraph's
  `astream(..., stream_mode="updates")` and forwards every node's `events`
  list as JSON frames. The frontend uses these events to highlight nodes in
  the ReactFlow graph in real time.
- **`query`** — the streamer is the dedicated
  `stream_open_query_frames(...)` generator (see `app/moa/open_query.py`).
  It runs `agent.astream_events(version="v2")` and re-emits each
  `on_tool_end` event as an `AgentEvent` with `type="tool"`, so the frontend
  renders an MCP tool timeline that ticks live as the agent reasons.
  The input supports either a single `query` or a full `messages` array
  (`[{role, content}, ...]`) for multi-turn chat context.

Frame schema:

```jsonc
{"kind": "started", "at": "...", "mode": "brief"}
{"kind": "event",   "event": <AgentEvent>}
{"kind": "node_done", "node": "scores"}
{"kind": "result", "result": <RunResult>}
{"kind": "error", "message": "..."}
```

## Comparing modes

The `compare` mode runs the **full MoA** alongside a **single-model
baseline** (`deepseek/deepseek-chat-v3.1` answering directly). Both run in
parallel inside the same graph: `kickoff` fans out to the proposers *and* to
the `baseline` node, the proposers feed the refiners and the editor, and the
baseline goes straight to `END`. The UI shows them side by side. This is the
highest-leverage demo: it exposes when MoA actually adds value vs. just
costing more tokens.

## Hybrid orchestration

The project deliberately uses *two* orchestration patterns:

- **`brief` and `compare`** use the deterministic MoA LangGraph (great for
  repeatable daily recaps where you want each section to come from a
  dedicated specialist).
- **`query`** powers NBA Copilot using a tool-using LangChain
  agent (`create_agent`) with the full MCP toolset minus a small blocklist
  for endpoints that 401 on the free balldontlie plan
  (`nba_stats_player_season_averages`, `nba_stats_player_stats_by_name`).
  The agent can plan tool calls dynamically for open-ended questions across
  multi-turn chat history, and its tool decisions are streamed live to the
  frontend.

Both share the same `RunResult` schema and the same WebSocket frame
protocol, so the frontend can render either mode without special-casing the
transport.

## Source traceability

Every pipeline run is observed by a request-scoped `RunTracker`
(`app/eval/tracker.py`, bound via `ContextVar` in `app/api/runner.py`). In
addition to token/cost/latency metrics, the tracker maintains a numbered
list of `SourceCitation` records (`app/eval/schemas.py`, helpers in
`app/moa/citations.py`).

Each citation captures:

| Field | Meaning |
|-------|---------|
| `id` | Monotonic integer per run (`1`, `2`, `3`, …) — used for inline `[n]` refs and UI linking |
| `provider` | Human label derived from the tool name (`ESPN`, `Reddit`, `balldontlie`) |
| `tool` | MCP tool name (e.g. `espn_nba_headlines`) |
| `agent` | Logical agent that invoked the tool (`news`, `nba_copilot`, …) |
| `retrieved_at` | Wall-clock time when the MCP call completed |
| `url` | First HTTP link extracted from the tool JSON, if any |
| `title` | Short human-readable label (often derived from tool + args) |
| `excerpt` | Truncated preview of the raw MCP payload (~280 chars) |

### Recording path

```
MCP tool returns raw JSON/text
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  mcp_invoke (proposers)          record_streamed_tool_call │
│  scores, news, injuries, social  (nba_copilot streaming)   │
└───────────────────────────┬───────────────────────────────┘
                            ▼
              RunTracker.record_mcp_citation()
              (+ record_tool_call for eval metrics)
                            ▼
              AgentEvent type="tool" with citation_id, provider, …
                            ▼
              (brief/compare) proposals may also carry legacy
              source strings → merged at the end
```

- **Direct-tool proposers** go through `mcp_invoke` in `app/moa/agents/base.py`.
  On success, `record_mcp_citation()` parses URLs from the payload
  (`urls_from_payload`) and assigns the next `id`.
- **NBA Copilot** records citations inside `record_streamed_tool_call` on each
  `on_tool_end` from `astream_events`. The streamed `AgentEvent` picks up
  metadata via `_latest_citation_fields()` in `app/moa/open_query.py`.
- **Legacy proposal URLs** — proposers like `news` still attach ESPN links in
  `AgentProposal.sources`. `merge_run_citations()` deduplicates these against
  MCP citations so the bibliography is complete even when a URL only appeared
  in the proposal layer.

### Attaching the bibliography to the API response

After the pipeline finishes, `runner._attach_citations()` builds the final
list:

```python
result.source_citations = merge_run_citations(tracker, proposals)
```

This runs for `brief`, `compare`, and `query`. The frontend renders it in the
**Sources** panel (`SourcesBibliography`) and uses the same ids in the MCP
tool timeline.

### Daily Brief — inline `[n]` citations (editor pass)

The MoA graph does **not** write the user-facing brief. Layer-1/2 agents
produce drafts; `editor_agent` (`app/moa/agents/editor.py`) is a separate
LLM call that runs **after** all MCP tools have completed.

At editor time:

1. `merge_run_citations(tracker, state["proposals"])` collects every MCP
   citation plus any proposal-only URLs.
2. `format_citation_index(citations)` renders a numbered block, e.g.
   `[1] ESPN — espn_nba_headlines — news — 2026-05-18 12:00 UTC | https://…`
3. That block is appended to the **user** prompt, and `BRIEF_SYSTEM` instructs
   the editor to add inline `[n]` when stating facts grounded in the drafts.
4. The frontend (`CitedMarkdown`) turns `[n]` into clickable links that scroll
   to `#source-n` and highlight the matching tool step (`citation_id === n`).

So for the brief, association between prose and sources is **delegated to the
editor LLM** with an explicit numbered index — not computed by semantic
matching in Python.

### NBA Copilot — bibliography without pre-injected index

NBA Copilot does **not** follow the editor pattern:

| Step | What the model sees |
|------|---------------------|
| System prompt | `NBA_COPILOT_SYSTEM_BASE` in `open_query.py` — rules for tools + a line asking for `[n]` tied to *"the source index provided in the user message"* |
| User messages | Only the chat history from `_build_input_messages` — **no** `format_citation_index` block |
| During the run | Raw `ToolMessage` payloads inside the ReAct loop (the model reads JSON directly) |
| After the run | `source_citations` attached in `runner._attach_citations` for the UI |

Implications:

- The **Sources** section and MCP timeline are reliable (built from the tracker).
- Inline `[n]` in Copilot answers are **best-effort** today: the system prompt
  references an index that is never injected into the chat messages.
- A planned improvement is a **post-pass** (second LLM call after tools finish)
  that supplies `format_citation_index` and asks the model to rewrite the answer
  with valid `[n]` markers — same mechanism as the editor, but after the
  tool-using loop.

### What is not implemented yet

- **Semantic phrase → tool output** — clicking an arbitrary sentence and
  recovering the exact MCP JSON chunk without an `[n]` marker in the text.
- **Copilot post-pass** — numbered index injected after tool calls complete.

## Brief memory (NBA Copilot RAG)

Past **Daily Brief** runs are indexed for semantic retrieval so NBA Copilot
can answer trend questions (“why is everyone talking about the Pacers this
week?”) without relying only on live MCP calls.

```
Daily Brief completes
        │
        ▼
runner._index_brief_memory  ──►  MemoryService.index_brief
        │                              │
        │                              ├─ chunk_brief_markdown (by ## section)
        │                              ├─ embed_texts (OpenRouter embeddings API)
        │                              └─ MemoryRepository → Postgres + pgvector
        │
NBA Copilot (query mode)
        │
        ├─ MCP tools (live data)
        └─ search_brief_memory (LangChain StructuredTool)
                 │
                 ▼
           cosine similarity + keyword fallback
                 │
                 ▼
           formatted excerpts in tool result
```

| Piece | Location |
|-------|----------|
| Chunking | `app/memory/chunking.py` |
| Embeddings | `app/memory/embeddings.py` (`openai/text-embedding-3-small` via OpenRouter) |
| Storage | `app/memory/repository.py` + `app/memory/models.py` — Postgres `briefs` + `chunks`, `chunks.embedding` as `vector(1536)` |
| Copilot tool | `app/memory/tool.py` — `search_brief_memory(query, days=14)` |
| Auto-index | `app/api/runner.py` after each successful `brief` run |
| Config | `MEMORY_*` env vars in `.env.example` |
| Schema | Alembic; `AUTO_MIGRATE=true` runs `upgrade head` in FastAPI lifespan (`app/db/migrate.py`) |

Temporal filter: the `days` argument on the tool (and `MEMORY_DEFAULT_DAYS`)
limits chunks by brief `date`. Live scores and breaking news should still
come from MCP tools; memory supplies narrative context from prior briefs.

## Brief output structure

The `editor` agent uses an explicit markdown template so the daily brief is
always shaped the same way:

```
# Last Night in the NBA — {date}
## Quick Hits           (≤3 bullets)
## Box Score Recap      (2 short paragraphs)
## Standout Statlines   (2-4 bullets, EXACT statlines from the stats agent)
## Trades, Rumors & News (verified items only)
## Injuries Watch       (verified statuses only)
## Storyline of the Night (2 paragraphs from the narrative agent)
## Fan Pulse            (1 paragraph from the social agent)
```

Sections without data are filled with `"No notable items today."` instead of
being skipped. The Standout Statlines section is the one that consumes the
boxscore-grounded output of the tool-using `stats` proposer — that's why
adding ESPN's `nba_boxscore` tool changed the perceived quality of the
brief more than any prompt tweak.

The editor is also instructed to add inline `[n]` citations (see "Source
traceability") when a fact comes from a specific reporter draft, using only
ids from the source index provided in its prompt.
