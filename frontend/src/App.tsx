import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import {
  type ChatMessage,
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
  query: "NBA Copilot",
  compare: "MoA vs Single LLM",
};

const MODE_DESCRIPTIONS: Record<Mode, string> = {
  brief: "One-click NBA briefing for last night's action.",
  query: "Chat with NBA Copilot — a tool-using MCP research assistant.",
  compare: "Daily Brief showdown: a single LLM vs the full MoA pipeline.",
};

export default function App() {
  const [mode, setMode] = useState<Mode>("brief");
  const [query, setQuery] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
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

  function resetRunArtifacts() {
    setStatuses({});
    setEvents([]);
    setResult(null);
  }

  function resetConversation() {
    resetRunArtifacts();
    setChatMessages([]);
    setQuery("");
  }

  function start() {
    if (running) return;
    const trimmedQuery = query.trim();
    if (mode === "query" && trimmedQuery.length < 3) {
      return;
    }
    resetRunArtifacts();

    let messagesForQuery: ChatMessage[] = [];
    if (mode === "query") {
      const userMessage: ChatMessage = { role: "user", content: trimmedQuery };
      messagesForQuery = [...chatMessages, userMessage];
      setChatMessages(messagesForQuery);
      setQuery("");
    }

    setRunning(true);
    streamRun({
      mode,
      query: mode === "query" ? "" : trimmedQuery,
      messages: mode === "query" ? messagesForQuery : [],
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
          if (mode === "query") {
            setChatMessages((prev) => [
              ...prev,
              { role: "assistant", content: frame.result.final_brief || "(empty)" },
            ]);
          }
          setRunning(false);
        } else if (frame.kind === "error") {
          setRunning(false);
        }
      },
    });
  }

  return (
    <div className="relative min-h-screen bg-ink overflow-hidden">
      <img
        src="/lebron.png"
        alt=""
        aria-hidden="true"
        className="pointer-events-none select-none hidden xl:block absolute left-0 top-40 h-[520px] w-auto opacity-200 z-0"
      />
      <img
        src="/wemby-clean.png"
        alt=""
        aria-hidden="true"
        className="pointer-events-none select-none hidden xl:block absolute right-0 top-40 h-[460px] w-auto opacity-200 z-0"
      />
      <img
        src="/luka-clean.png"
        alt=""
        aria-hidden="true"
        className="pointer-events-none select-none hidden xl:block absolute left-2 -bottom-10 h-[500px] w-auto opacity-200 z-0"
      />
      <img
        src="/shai-clean.png"
        alt=""
        aria-hidden="true"
        className="pointer-events-none select-none hidden xl:block absolute right-2 -bottom-10 h-[500px] w-auto opacity-200 z-0"
      />
      <div className="absolute inset-0 bg-gradient-to-r from-ink/85 via-ink/55 to-ink/85 pointer-events-none z-0" />
      <div className="relative z-10">
        <Header health={health} />
      </div>

      <main className="relative z-10 max-w-7xl mx-auto px-6 py-6 space-y-6">
        <ModeTabs mode={mode} onChange={setMode} disabled={running} />

        <div className="card flex flex-col md:flex-row md:items-center gap-3">
          {mode === "query" && (
            <input
              className="input flex-1"
              placeholder="Ask an NBA question..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={running}
              onKeyDown={(e) => e.key === "Enter" && start()}
            />
          )}
          <button className="btn" onClick={start} disabled={running}>
            {running ? "In progress..." : mode === "query" ? "Send" : "Run pipeline"}
          </button>
          {(result || chatMessages.length > 0) && (
            <button
              className="btn-secondary"
              onClick={resetConversation}
              disabled={running}
              title="Clear and start fresh"
            >
              Reset
            </button>
          )}
        </div>

        {mode === "query" ? (
          <section className="space-y-4">
            <div>
              <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-2">
                Chat
              </h2>
              <ChatTranscript messages={chatMessages} running={running} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-2">
                  MCP tool timeline
                </h2>
                <ToolTimeline events={events} running={running} />
              </div>
              <div>
                <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-2">
                  Live trace
                </h2>
                <EventLog events={events} />
              </div>
            </div>
          </section>
        ) : (
          <section className="space-y-6">
            <div>
              <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-2">
                Agent graph
              </h2>
              <AgentFlow statuses={statuses} models={models} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-2">
                  MCP tool timeline
                </h2>
                <ToolTimeline events={events} running={running} />
              </div>
              <div>
                <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-2">
                  Live trace
                </h2>
                <EventLog events={events} />
              </div>
            </div>
          </section>
        )}

        {result && mode !== "query" && <ResultPanel result={result} mode={mode} />}

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
        <div className="flex items-center gap-4">
          <img
            src="/basketball-cutout.png"
            alt="Basketball icon"
            className="h-28 w-auto drop-shadow-sm"
          />
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              NBA <span className="text-accent">MCP & Mixture of Agents</span>
            </h1>
            <p className="text-base text-muted mt-1">
              Nightly NBA briefing and research workspace.
            </p>
            <p
              className={clsx("text-sm mt-1", {
                "text-emerald-700": coreReady && !optionalMissing,
                "text-amber-700": coreReady && optionalMissing,
                "text-red-700": !coreReady,
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
                title="Optional: used by some NBA stats endpoints in NBA Copilot"
              />
              <HealthPill
                ok={health?.mcp_initialised}
                label={`MCP (${toolCount} tools)`}
                title={health?.mcp_tools.join(", ")}
              />
            </div>
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
        "border-emerald-300 bg-emerald-50 text-emerald-700": state === "ok",
        "border-red-300 bg-red-50 text-red-700": state === "fail" || state === "optional-missing",
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
            "card text-left transition border hover:shadow-md",
            m === mode
              ? "border-accent bg-amber-50 shadow-sm"
              : "hover:border-slate-300",
          )}
        >
          <div className="text-lg font-semibold">{MODE_LABELS[m]}</div>
          <div className="text-base text-muted mt-1">{MODE_DESCRIPTIONS[m]}</div>
        </button>
      ))}
    </div>
  );
}

function ResultPanel({ result, mode }: { result: RunResult; mode: Mode }) {
  const toolCalls = result.events.filter((e) => e.type === "tool").length;
  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3 text-base text-muted">
        <span>
          Done in <strong className="text-slate-900 text-lg">{result.duration_seconds.toFixed(1)}s</strong>
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
            <h3 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-3">
              Single LLM (baseline)
            </h3>
            <Markdown content={result.single_llm_answer || "(empty)"} />
          </div>
          <div className="card border-accent/40 bg-amber-50/60">
            <h3 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-accent mb-3">
              Mixture of Agents
            </h3>
            <Markdown content={result.final_brief || "(empty)"} />
          </div>
        </div>
      ) : (
        <div className="card">
          <h3 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-accent mb-3">
            Final {mode === "brief" ? "briefing" : "answer"}
          </h3>
          <Markdown content={result.final_brief || "(empty)"} />
        </div>
      )}

      {mode !== "query" && (
        <details className="card">
          <summary className="cursor-pointer text-lg font-semibold text-slate-900">
            Raw proposals & refinements ({result.proposals.length + result.refinements.length})
          </summary>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {result.proposals.map((p) => (
              <div key={p.agent} className="rounded-lg border border-border p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-slate-900 text-base">{p.agent}</span>
                  <span className="text-xs font-mono text-muted">{p.model}</span>
                </div>
                <p className="text-sm text-slate-700 whitespace-pre-wrap">{p.summary}</p>
              </div>
            ))}
            {result.refinements.map((r) => (
              <div
                key={r.agent}
                className="rounded-lg border border-sky-300 bg-sky-50 p-3"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-sky-700 text-base">{r.agent}</span>
                  <span className="text-xs font-mono text-muted">{r.model}</span>
                </div>
                <p className="text-sm text-slate-700 whitespace-pre-wrap">{r.content}</p>
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
        <span className="pill border-amber-300 bg-amber-50 text-amber-700">
          {steps.length} tool call(s)
        </span>
        {running && <span className="pill">running</span>}
        {hasError && <span className="pill border-red-300 bg-red-50 text-red-700">error</span>}
      </div>

      {!started && (
        <p className="text-base text-muted italic">
          Send a message to see which MCP tools NBA Copilot decides to use.
        </p>
      )}

      {started && steps.length === 0 && !hasError && (
        <p className="text-base text-muted italic">
          Agent started. Waiting for first tool decision...
        </p>
      )}

      <div className="space-y-3">
        {steps.map((s, idx) => (
          <div key={`${s.at}-${idx}`} className="rounded-lg border border-border p-3 bg-slate-50">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-mono text-amber-700">{s.tool}</span>
              <span className="text-xs text-muted">{s.at}</span>
            </div>
            <p className="text-sm text-slate-700 mt-2 whitespace-pre-wrap">{s.preview}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChatTranscript({
  messages,
  running,
}: {
  messages: ChatMessage[];
  running: boolean;
}) {
  return (
    <div className="card h-[420px] overflow-y-auto space-y-3">
      {messages.length === 0 && (
        <p className="text-base text-muted italic">
          Start a conversation with NBA Copilot.
        </p>
      )}
      {messages.map((message, idx) => (
        <div
          key={`${message.role}-${idx}`}
          className={clsx("rounded-lg border p-3", {
            "border-accent/40 bg-amber-50/50": message.role === "assistant",
            "border-border bg-slate-50": message.role === "user",
          })}
        >
          <div className="text-xs uppercase tracking-[0.08em] text-muted mb-1">
            {message.role === "user" ? "You" : "Assistant"}
          </div>
          {message.role === "assistant" ? (
            <Markdown content={message.content} />
          ) : (
            <p className="text-sm text-slate-800 whitespace-pre-wrap">{message.content}</p>
          )}
        </div>
      ))}
      {running && <p className="text-sm text-muted italic">Assistant is thinking...</p>}
    </div>
  );
}

function Footer() {
  return (
    <footer className="text-sm text-muted text-center py-6 border-t border-border mt-2">
      Built with LangGraph · OpenRouter · Model Context Protocol · React Flow
    </footer>
  );
}
