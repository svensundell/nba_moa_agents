import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import {
  type ChatMessage,
  type LanguageCode,
  fetchAgents,
  fetchHealth,
  streamRun,
  type AgentEvent,
  type AgentMeta,
  type HealthInfo,
  type RunResult,
} from "./api";
import { AgentFlow, type AgentStatus } from "./components/AgentFlow";
import { EvalDashboard } from "./components/EvalDashboard";
import { EventLog } from "./components/EventLog";
import { Markdown } from "./components/Markdown";
import { RunMetricsPanel } from "./components/RunMetricsPanel";

type Mode = "brief" | "query" | "compare" | "eval";

const UI_TEXT: Record<
  LanguageCode,
  {
    modeLabels: Record<Mode, string>;
    modeDescriptions: Record<Mode, string>;
    askPlaceholder: string;
    send: string;
    runPipeline: string;
    reset: string;
    inProgress: string;
    chat: string;
    mcpTimeline: string;
    liveTrace: string;
    agentGraph: string;
    doneIn: string;
    toolCalls: string;
    proposers: string;
    refiners: string;
    singleLlm: string;
    moa: string;
    finalBriefing: string;
    finalAnswer: string;
    rawSection: string;
    footer: string;
    healthCoreConnected: string;
    healthCoreConnectedOptional: string;
    healthDisconnected: string;
    healthBallTitle: string;
    toolTimelineIdle: string;
    toolTimelineWaiting: string;
    chatEmpty: string;
    userLabel: string;
    assistantLabel: string;
    assistantThinking: string;
  }
> = {
  en: {
    modeLabels: {
      brief: "Daily Brief",
      query: "NBA Copilot",
      compare: "MoA vs Single LLM",
      eval: "Evaluation",
    },
    modeDescriptions: {
      brief: "One-click NBA briefing for last night's action.",
      query: "Chat with NBA Copilot - a tool-using MCP research assistant.",
      compare: "Daily Brief showdown: a single LLM vs the full MoA pipeline.",
      eval: "Cost, latency, tool reliability and source coverage per run.",
    },
    askPlaceholder: "Ask an NBA question...",
    send: "Send",
    runPipeline: "Run pipeline",
    reset: "Reset",
    inProgress: "In progress...",
    chat: "Chat",
    mcpTimeline: "MCP tool timeline",
    liveTrace: "Live trace",
    agentGraph: "Agent graph",
    doneIn: "Done in",
    toolCalls: "MCP tool call(s)",
    proposers: "proposers",
    refiners: "refiners",
    singleLlm: "Single LLM (baseline)",
    moa: "Mixture of Agents",
    finalBriefing: "Final briefing",
    finalAnswer: "Final answer",
    rawSection: "Raw proposals & refinements",
    footer: "Built with LangGraph - OpenRouter - Model Context Protocol - React Flow",
    healthCoreConnected: "All data providers connected.",
    healthCoreConnectedOptional: "Core providers connected. Optional provider missing: balldontlie.",
    healthDisconnected: "Some core providers are not connected.",
    healthBallTitle: "Optional: used by some NBA stats endpoints in NBA Copilot",
    toolTimelineIdle: "Send a message to see which MCP tools NBA Copilot decides to use.",
    toolTimelineWaiting: "Agent started. Waiting for first tool decision...",
    chatEmpty: "Start a conversation with NBA Copilot.",
    userLabel: "You",
    assistantLabel: "Assistant",
    assistantThinking: "Assistant is thinking...",
  },
  fr: {
    modeLabels: {
      brief: "Brief quotidien",
      query: "NBA Copilot",
      compare: "MoA vs LLM unique",
      eval: "Évaluation",
    },
    modeDescriptions: {
      brief: "Un clic pour resumer les matchs de la veille.",
      query: "Discutez avec NBA Copilot, un assistant MCP avec outils.",
      compare: "Comparaison brief quotidien : LLM unique vs pipeline MoA.",
      eval: "Coût, latence, fiabilité des outils et couverture des sources par run.",
    },
    askPlaceholder: "Posez une question NBA...",
    send: "Envoyer",
    runPipeline: "Lancer le pipeline",
    reset: "Reinitialiser",
    inProgress: "En cours...",
    chat: "Chat",
    mcpTimeline: "Timeline des outils MCP",
    liveTrace: "Trace en direct",
    agentGraph: "Graphe des agents",
    doneIn: "Termine en",
    toolCalls: "appel(s) d'outils MCP",
    proposers: "proposers",
    refiners: "refiners",
    singleLlm: "LLM unique (baseline)",
    moa: "Mixture of Agents",
    finalBriefing: "Brief final",
    finalAnswer: "Reponse finale",
    rawSection: "Proposals & refinements bruts",
    footer: "Construit avec LangGraph - OpenRouter - Model Context Protocol - React Flow",
    healthCoreConnected: "Tous les fournisseurs de donnees sont connectes.",
    healthCoreConnectedOptional:
      "Fournisseurs principaux connectes. Fournisseur optionnel manquant : balldontlie.",
    healthDisconnected: "Certains fournisseurs principaux ne sont pas connectes.",
    healthBallTitle: "Optionnel : utilise par certains endpoints NBA Stats dans NBA Copilot",
    toolTimelineIdle:
      "Envoyez un message pour voir quels outils MCP NBA Copilot decide d'utiliser.",
    toolTimelineWaiting: "Agent demarre. En attente de la premiere decision d'outil...",
    chatEmpty: "Demarrez une conversation avec NBA Copilot.",
    userLabel: "Vous",
    assistantLabel: "Assistant",
    assistantThinking: "Assistant en train de reflechir...",
  },
};

export default function App() {
  const [language, setLanguage] = useState<LanguageCode>("fr");
  const [mode, setMode] = useState<Mode>("brief");
  const [query, setQuery] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [running, setRunning] = useState(false);
  const [statuses, setStatuses] = useState<Record<string, AgentStatus>>({});
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [result, setResult] = useState<RunResult | null>(null);
  const [agents, setAgents] = useState<AgentMeta[]>([]);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const ui = UI_TEXT[language];

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
    if (mode === "eval") return;
    const activeMode: "brief" | "query" | "compare" = mode;
    const trimmedQuery = query.trim();
    if (activeMode === "query" && trimmedQuery.length < 3) {
      return;
    }
    resetRunArtifacts();

    let messagesForQuery: ChatMessage[] = [];
    if (activeMode === "query") {
      const userMessage: ChatMessage = { role: "user", content: trimmedQuery };
      messagesForQuery = [...chatMessages, userMessage];
      setChatMessages(messagesForQuery);
      setQuery("");
    }

    setRunning(true);
    streamRun({
      mode: activeMode,
      language,
      query: activeMode === "query" ? "" : trimmedQuery,
      messages: activeMode === "query" ? messagesForQuery : [],
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
          if (activeMode === "query") {
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
        <Header health={health} language={language} setLanguage={setLanguage} ui={ui} />
      </div>

      <main className="relative z-10 max-w-7xl mx-auto px-6 py-6 space-y-6">
        <ModeTabs
          mode={mode}
          onChange={setMode}
          disabled={running}
          labels={ui.modeLabels}
          descriptions={ui.modeDescriptions}
        />

        {mode !== "eval" && (
          <div className="card flex flex-col md:flex-row md:items-center gap-3">
            {mode === "query" && (
              <input
                className="input flex-1"
                placeholder={ui.askPlaceholder}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={running}
                onKeyDown={(e) => e.key === "Enter" && start()}
              />
            )}
            <button className="btn" onClick={start} disabled={running}>
              {running ? ui.inProgress : mode === "query" ? ui.send : ui.runPipeline}
            </button>
            {(result || chatMessages.length > 0) && (
              <button
                className="btn-secondary"
                onClick={resetConversation}
                disabled={running}
                title={ui.reset}
              >
                {ui.reset}
              </button>
            )}
          </div>
        )}

        {mode === "eval" ? (
          <EvalDashboard language={language} />
        ) : mode === "query" ? (
          <section className="space-y-4">
            <div>
              <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-2">
                  {ui.chat}
              </h2>
              <ChatTranscript messages={chatMessages} running={running} ui={ui} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-2">
                  {ui.mcpTimeline}
                </h2>
                <ToolTimeline events={events} running={running} ui={ui} />
              </div>
              <div>
                <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-2">
                  {ui.liveTrace}
                </h2>
                <EventLog events={events} />
              </div>
            </div>
          </section>
        ) : (
          <section className="space-y-6">
            <div>
              <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-2">
                {ui.agentGraph}
              </h2>
              <AgentFlow statuses={statuses} models={models} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-2">
                  {ui.mcpTimeline}
                </h2>
                <ToolTimeline events={events} running={running} ui={ui} />
              </div>
              <div>
                <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-2">
                  {ui.liveTrace}
                </h2>
                <EventLog events={events} />
              </div>
            </div>
          </section>
        )}

        {result && mode !== "query" && mode !== "eval" && (
          <ResultPanel result={result} mode={mode} ui={ui} />
        )}

        {result?.metrics && mode !== "eval" && (
          <RunMetricsPanel metrics={result.metrics} language={language} />
        )}

        <Footer ui={ui} />
      </main>
    </div>
  );
}

function Header({
  health,
  language,
  setLanguage,
  ui,
}: {
  health: HealthInfo | null;
  language: LanguageCode;
  setLanguage: (language: LanguageCode) => void;
  ui: (typeof UI_TEXT)["en"];
}) {
  const toolCount = health?.mcp_tools.length ?? 0;
  const coreReady = Boolean(health?.has_openrouter) && Boolean(health?.mcp_initialised);
  const optionalMissing = health?.has_balldontlie === false;

  const statusText = coreReady
    ? optionalMissing
      ? ui.healthCoreConnectedOptional
      : ui.healthCoreConnected
    : ui.healthDisconnected;

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
              {language === "fr"
                ? "Espace de brief NBA quotidien et de recherche."
                : "Nightly NBA briefing and research workspace."}
            </p>
            <div className="mt-2 flex gap-2">
              <button
                className={clsx("pill", {
                  "border-accent bg-amber-50 text-amber-700": language === "fr",
                  "border-border text-muted": language !== "fr",
                })}
                onClick={() => setLanguage("fr")}
                type="button"
              >
                FR
              </button>
              <button
                className={clsx("pill", {
                  "border-accent bg-amber-50 text-amber-700": language === "en",
                  "border-border text-muted": language !== "en",
                })}
                onClick={() => setLanguage("en")}
                type="button"
              >
                EN
              </button>
            </div>
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
                title={ui.healthBallTitle}
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
  labels,
  descriptions,
}: {
  mode: Mode;
  onChange: (m: Mode) => void;
  disabled: boolean;
  labels: Record<Mode, string>;
  descriptions: Record<Mode, string>;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {(Object.keys(labels) as Mode[]).map((m) => (
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
          <div className="text-lg font-semibold">{labels[m]}</div>
          <div className="text-base text-muted mt-1">{descriptions[m]}</div>
        </button>
      ))}
    </div>
  );
}

function ResultPanel({
  result,
  mode,
  ui,
}: {
  result: RunResult;
  mode: Mode;
  ui: (typeof UI_TEXT)["en"];
}) {
  const toolCalls = result.events.filter((e) => e.type === "tool").length;
  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3 text-base text-muted">
        <span>
          {ui.doneIn}{" "}
          <strong className="text-slate-900 text-lg">{result.duration_seconds.toFixed(1)}s</strong>
        </span>
        <span>•</span>
        {mode === "query" ? (
          <span>
            {toolCalls} {ui.toolCalls}
          </span>
        ) : (
          <>
            <span>
              {result.proposals.length} {ui.proposers}
            </span>
            <span>•</span>
            <span>
              {result.refinements.length} {ui.refiners}
            </span>
          </>
        )}
      </div>

      {mode === "compare" ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card">
            <h3 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-3">
              {ui.singleLlm}
            </h3>
            <Markdown content={result.single_llm_answer || "(empty)"} />
          </div>
          <div className="card border-accent/40 bg-amber-50/60">
            <h3 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-accent mb-3">
              {ui.moa}
            </h3>
            <Markdown content={result.final_brief || "(empty)"} />
          </div>
        </div>
      ) : (
        <div className="card">
          <h3 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-accent mb-3">
            {mode === "brief" ? ui.finalBriefing : ui.finalAnswer}
          </h3>
          <Markdown content={result.final_brief || "(empty)"} />
        </div>
      )}

      {mode !== "query" && (
        <details className="card">
          <summary className="cursor-pointer text-lg font-semibold text-slate-900">
            {ui.rawSection} ({result.proposals.length + result.refinements.length})
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
  ui,
}: {
  events: AgentEvent[];
  running: boolean;
  ui: (typeof UI_TEXT)["en"];
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
          {ui.toolTimelineIdle}
        </p>
      )}

      {started && steps.length === 0 && !hasError && (
        <p className="text-base text-muted italic">
          {ui.toolTimelineWaiting}
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
  ui,
}: {
  messages: ChatMessage[];
  running: boolean;
  ui: (typeof UI_TEXT)["en"];
}) {
  return (
    <div className="card h-[420px] overflow-y-auto space-y-3">
      {messages.length === 0 && (
        <p className="text-base text-muted italic">
          {ui.chatEmpty}
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
            {message.role === "user" ? ui.userLabel : ui.assistantLabel}
          </div>
          {message.role === "assistant" ? (
            <Markdown content={message.content} />
          ) : (
            <p className="text-sm text-slate-800 whitespace-pre-wrap">{message.content}</p>
          )}
        </div>
      ))}
      {running && <p className="text-sm text-muted italic">{ui.assistantThinking}</p>}
    </div>
  );
}

function Footer({ ui }: { ui: (typeof UI_TEXT)["en"] }) {
  return (
    <footer className="text-sm text-muted text-center py-6 border-t border-border mt-2">
      {ui.footer}
    </footer>
  );
}
