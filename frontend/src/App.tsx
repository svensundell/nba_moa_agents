import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import {
  fetchAgents,
  fetchHealth,
  streamRun,
  type AgentEvent,
  type AgentMeta,
  type HealthInfo,
  type RunResult,
} from "./api";
import { AgentFlow, type AgentStatus } from "./components/AgentFlow";
import { EventLog } from "./components/EventLog";
import { Markdown } from "./components/Markdown";

type Mode = "brief" | "query" | "compare";

const MODE_LABELS: Record<Mode, string> = {
  brief: "Daily Brief",
  query: "Ask Anything",
  compare: "MoA vs Single LLM",
};

const MODE_DESCRIPTIONS: Record<Mode, string> = {
  brief: "One-click NBA briefing for last night's action.",
  query: "Ask any NBA question, answered by a tool-using MCP research agent.",
  compare: "Daily Brief showdown: a single LLM vs the full MoA pipeline.",
};

export default function App() {
  const [mode, setMode] = useState<Mode>("brief");
  const [query, setQuery] = useState("");
  const [running, setRunning] = useState(false);
  const [statuses, setStatuses] = useState<Record<string, AgentStatus>>({});
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [result, setResult] = useState<RunResult | null>(null);
  const [agents, setAgents] = useState<AgentMeta[]>([]);
  const [health, setHealth] = useState<HealthInfo | null>(null);

  useEffect(() => {
    fetchAgents().then(setAgents).catch(() => setAgents([]));
    fetchHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  const models = useMemo(() => {
    const map: Record<string, string> = {};
    for (const a of agents) map[a.agent] = a.provider_model;
    return map;
  }, [agents]);

  function reset() {
    setStatuses({});
    setEvents([]);
    setResult(null);
  }

  function start() {
    if (running) return;
    if (mode === "query" && query.trim().length < 3) {
      return;
    }
    reset();
    setRunning(true);

    streamRun({
      mode,
      query: mode === "query" ? query : "",
      onFrame: (frame) => {
        if (frame.kind === "started") {
          setStatuses((s) => ({ ...s, kickoff: "running" }));
        } else if (frame.kind === "event") {
          setEvents((prev) => [...prev, frame.event]);
          if (frame.event.type === "done") {
            setStatuses((s) => ({ ...s, [frame.event.agent]: "done" }));
          } else if (frame.event.type === "error") {
            setStatuses((s) => ({ ...s, [frame.event.agent]: "error" }));
          } else if (frame.event.type === "start") {
            setStatuses((s) => ({ ...s, [frame.event.agent]: "running" }));
          }
        } else if (frame.kind === "node_done") {
          setStatuses((s) => ({ ...s, [frame.node]: "done" }));
        } else if (frame.kind === "result") {
          setResult(frame.result);
          setRunning(false);
        } else if (frame.kind === "error") {
          setRunning(false);
        }
      },
    });
  }

  return (
    <div className="min-h-screen">
      <Header health={health} />

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        <ModeTabs mode={mode} onChange={setMode} disabled={running} />

        <div className="card flex flex-col md:flex-row md:items-center gap-3">
          {mode === "query" && (
            <input
              className="input flex-1"
              placeholder="e.g. How is Luka Doncic playing this season?"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={running}
              onKeyDown={(e) => e.key === "Enter" && start()}
            />
          )}
          <button className="btn" onClick={start} disabled={running}>
            {running ? "In progress..." : "Run pipeline"}
          </button>
          {result && (
            <button
              className="btn-secondary"
              onClick={reset}
              disabled={running}
              title="Clear and start fresh"
            >
              Reset
            </button>
          )}
        </div>

        {mode === "query" ? (
          <section className="grid gap-4 lg:grid-cols-2">
            <div>
              <h2 className="text-sm uppercase tracking-wide text-muted mb-2">
                MCP tool timeline
              </h2>
              <ToolTimeline events={events} running={running} />
            </div>
            <div>
              <h2 className="text-sm uppercase tracking-wide text-muted mb-2">
                Live trace
              </h2>
              <EventLog events={events} />
            </div>
          </section>
        ) : (
          <section className="space-y-6">
            <div>
              <h2 className="text-sm uppercase tracking-wide text-muted mb-2">
                Agent graph
              </h2>
              <AgentFlow statuses={statuses} models={models} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <h2 className="text-sm uppercase tracking-wide text-muted mb-2">
                  MCP tool timeline
                </h2>
                <ToolTimeline events={events} running={running} />
              </div>
              <div>
                <h2 className="text-sm uppercase tracking-wide text-muted mb-2">
                  Live trace
                </h2>
                <EventLog events={events} />
              </div>
            </div>
          </section>
        )}

        {result && <ResultPanel result={result} mode={mode} />}

        <Footer />
      </main>
    </div>
  );
}

function Header({ health }: { health: HealthInfo | null }) {
  const toolCount = health?.mcp_tools.length ?? 0;
  const coreReady = Boolean(health?.has_openrouter) && Boolean(health?.mcp_initialised);
  const optionalMissing = health?.has_balldontlie === false;

  const statusText = coreReady
    ? optionalMissing
      ? "Core providers connected. Optional provider missing: balldontlie."
      : "All data providers connected."
    : "Some core providers are not connected.";

  return (
    <header className="border-b border-border">
      <div className="max-w-7xl mx-auto px-6 py-4">
        <div>
          <h1 className="text-xl font-bold">
            NBA <span className="text-accent">Mixture of Agents</span>
          </h1>
          <p className="text-sm text-muted mt-1">
            Nightly NBA briefing and research workspace.
          </p>
          <p
            className={clsx("text-xs mt-1", {
              "text-emerald-300": coreReady && !optionalMissing,
              "text-amber-300": coreReady && optionalMissing,
              "text-red-300": !coreReady,
            })}
          >
            {statusText}
          </p>
          <div className="flex items-center gap-2 mt-2">
            <HealthPill ok={health?.has_openrouter} label="OpenRouter" />
            <HealthPill
              ok={health?.has_balldontlie}
              label="balldontlie"
              optional
              title="Optional: used by some NBA stats endpoints in Ask Anything"
            />
            <HealthPill
              ok={health?.mcp_initialised}
              label={`MCP (${toolCount} tools)`}
              title={health?.mcp_tools.join(", ")}
            />
          </div>
        </div>
      </div>
    </header>
  );
}

function HealthPill({
  ok,
  label,
  optional,
  title,
}: {
  ok: boolean | undefined;
  label: string;
  optional?: boolean;
  title?: string;
}) {
  const state =
    ok === undefined ? "neutral" : ok ? "ok" : optional ? "optional-missing" : "fail";
  return (
    <span
      className={clsx("pill", {
        "border-emerald-500/40 text-emerald-300": state === "ok",
        "border-red-500/40 text-red-300": state === "fail" || state === "optional-missing",
        "border-border text-muted": state === "neutral",
      })}
      title={title ?? (state === "fail" ? `${label} not configured` : "")}
    >
      {label}
    </span>
  );
}

function ModeTabs({
  mode,
  onChange,
  disabled,
}: {
  mode: Mode;
  onChange: (m: Mode) => void;
  disabled: boolean;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {(Object.keys(MODE_LABELS) as Mode[]).map((m) => (
        <button
          key={m}
          onClick={() => onChange(m)}
          disabled={disabled}
          className={clsx(
            "card text-left transition border",
            m === mode
              ? "border-accent bg-accent/10"
              : "hover:border-slate-500",
          )}
        >
          <div className="font-semibold">{MODE_LABELS[m]}</div>
          <div className="text-xs text-muted mt-1">{MODE_DESCRIPTIONS[m]}</div>
        </button>
      ))}
    </div>
  );
}

function ResultPanel({ result, mode }: { result: RunResult; mode: Mode }) {
  const toolCalls = result.events.filter((e) => e.type === "tool").length;
  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3 text-sm text-muted">
        <span>
          Done in <strong className="text-slate-200">{result.duration_seconds.toFixed(1)}s</strong>
        </span>
        <span>•</span>
        {mode === "query" ? (
          <span>{toolCalls} MCP tool call(s)</span>
        ) : (
          <>
            <span>{result.proposals.length} proposers</span>
            <span>•</span>
            <span>{result.refinements.length} refiners</span>
          </>
        )}
      </div>

      {mode === "compare" ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card">
            <h3 className="text-sm uppercase tracking-wide text-muted mb-3">
              Single LLM (baseline)
            </h3>
            <Markdown content={result.single_llm_answer || "(empty)"} />
          </div>
          <div className="card border-accent/40">
            <h3 className="text-sm uppercase tracking-wide text-accent mb-3">
              Mixture of Agents
            </h3>
            <Markdown content={result.final_brief || "(empty)"} />
          </div>
        </div>
      ) : (
        <div className="card">
          <h3 className="text-sm uppercase tracking-wide text-accent mb-3">
            Final {mode === "brief" ? "briefing" : "answer"}
          </h3>
          <Markdown content={result.final_brief || "(empty)"} />
        </div>
      )}

      {mode !== "query" && (
        <details className="card">
          <summary className="cursor-pointer font-semibold text-slate-200">
            Raw proposals & refinements ({result.proposals.length + result.refinements.length})
          </summary>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {result.proposals.map((p) => (
              <div key={p.agent} className="rounded-lg border border-border p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-slate-100 text-sm">{p.agent}</span>
                  <span className="text-[10px] font-mono text-muted">{p.model}</span>
                </div>
                <p className="text-xs text-slate-300 whitespace-pre-wrap">{p.summary}</p>
              </div>
            ))}
            {result.refinements.map((r) => (
              <div
                key={r.agent}
                className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-3"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-sky-200 text-sm">{r.agent}</span>
                  <span className="text-[10px] font-mono text-muted">{r.model}</span>
                </div>
                <p className="text-xs text-slate-300 whitespace-pre-wrap">{r.content}</p>
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

type ToolStep = {
  at: string;
  tool: string;
  preview: string;
};

function ToolTimeline({
  events,
  running,
}: {
  events: AgentEvent[];
  running: boolean;
}) {
  const steps = useMemo<ToolStep[]>(() => {
    return events
      .filter((e) => e.type === "tool")
      .map((e) => {
        const [left, ...rest] = e.content.split(":");
        const preview = rest.join(":").trim() || e.content;
        return {
          at: new Date(e.timestamp).toLocaleTimeString(),
          tool: left.trim(),
          preview,
        };
      });
  }, [events]);

  const hasError = events.some((e) => e.type === "error");
  const started = events.some((e) => e.type === "start");

  return (
    <div className="card h-[460px] overflow-y-auto">
      <div className="flex items-center gap-2 mb-3">
        <span className="pill border-fuchsia-500/40 text-fuchsia-200">
          {steps.length} tool call(s)
        </span>
        {running && <span className="pill">running</span>}
        {hasError && <span className="pill border-red-500/40 text-red-300">error</span>}
      </div>

      {!started && (
        <p className="text-sm text-muted italic">
          Run a query to see which MCP tools the ask-anything agent decides to use.
        </p>
      )}

      {started && steps.length === 0 && !hasError && (
        <p className="text-sm text-muted italic">
          Agent started. Waiting for first tool decision...
        </p>
      )}

      <div className="space-y-3">
        {steps.map((s, idx) => (
          <div key={`${s.at}-${idx}`} className="rounded-lg border border-border p-3 bg-ink/30">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-mono text-fuchsia-200">{s.tool}</span>
              <span className="text-[11px] text-muted">{s.at}</span>
            </div>
            <p className="text-xs text-slate-300 mt-2 whitespace-pre-wrap">{s.preview}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function Footer() {
  return (
    <footer className="text-xs text-muted text-center py-6 border-t border-border">
      Built with LangGraph · OpenRouter · Model Context Protocol · React Flow
    </footer>
  );
}
