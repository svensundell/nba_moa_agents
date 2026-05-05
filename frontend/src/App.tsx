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
  query: "Ask any NBA question — answered through 8 agents on 5 models.",
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
    for (const a of agents) map[a.agent] = a.groq_model;
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
            {running ? "Agents working..." : "Run pipeline"}
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

        <section className="grid gap-4 lg:grid-cols-2">
          <div>
            <h2 className="text-sm uppercase tracking-wide text-muted mb-2">
              Agent graph
            </h2>
            <AgentFlow statuses={statuses} models={models} />
          </div>
          <div>
            <h2 className="text-sm uppercase tracking-wide text-muted mb-2">
              Live trace
            </h2>
            <EventLog events={events} />
          </div>
        </section>

        {result && <ResultPanel result={result} mode={mode} />}

        <Footer />
      </main>
    </div>
  );
}

function Header({ health }: { health: HealthInfo | null }) {
  const toolCount = health?.mcp_tools.length ?? 0;
  const serverCount = health?.mcp_servers.length ?? 0;
  return (
    <header className="border-b border-border">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">
            NBA <span className="text-accent">Mixture of Agents</span>
          </h1>
          <p className="text-xs text-muted mt-0.5">
            8 specialised agents, 5 Groq models, {serverCount || 3} MCP servers — one briefing.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <HealthPill ok={health?.has_groq} label="Groq" />
          <HealthPill
            ok={health?.mcp_initialised}
            label={`MCP (${toolCount} tools)`}
            title={health?.mcp_tools.join(", ")}
          />
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
    ok === undefined ? "neutral" : ok ? "ok" : optional ? "optional" : "fail";
  return (
    <span
      className={clsx("pill", {
        "border-emerald-500/40 text-emerald-300": state === "ok",
        "border-red-500/40 text-red-300": state === "fail",
        "border-border text-muted": state === "optional" || state === "neutral",
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
  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3 text-sm text-muted">
        <span>
          Done in <strong className="text-slate-200">{result.duration_seconds.toFixed(1)}s</strong>
        </span>
        <span>•</span>
        <span>{result.proposals.length} proposers</span>
        <span>•</span>
        <span>{result.refinements.length} refiners</span>
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
    </section>
  );
}

function Footer() {
  return (
    <footer className="text-xs text-muted text-center py-6 border-t border-border">
      Built with LangGraph · Groq · Model Context Protocol · React Flow
    </footer>
  );
}
