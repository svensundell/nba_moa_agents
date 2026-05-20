import { useMemo } from "react";
import clsx from "clsx";
import type { LanguageCode, RunMetrics } from "../api";

type T = {
  title: string;
  totalCost: string;
  totalTokens: string;
  llmCalls: string;
  toolCalls: string;
  toolFailures: string;
  distinctSources: string;
  duration: string;
  perAgent: string;
  agent: string;
  model: string;
  llmCallsCol: string;
  inputTokens: string;
  outputTokens: string;
  costUsd: string;
  llmLatency: string;
  toolCallsCol: string;
  toolFailuresCol: string;
  toolLatency: string;
  wallClock: string;
  wallClockHelp: string;
  sources: string;
  estimatedNote: string;
  moaVsBaseline: string;
  moaPipeline: string;
  baselineLlm: string;
  noSources: string;
};

const COPY: Record<LanguageCode, T> = {
  en: {
    title: "Run metrics",
    totalCost: "Cost (USD)",
    totalTokens: "Tokens (in / out)",
    llmCalls: "LLM calls",
    toolCalls: "Tool calls",
    toolFailures: "Tool failures",
    distinctSources: "Distinct sources",
    duration: "Duration",
    perAgent: "Per-agent breakdown",
    agent: "Agent",
    model: "Model",
    llmCallsCol: "LLM",
    inputTokens: "In",
    outputTokens: "Out",
    costUsd: "$",
    llmLatency: "LLM ms",
    toolCallsCol: "Tools",
    toolFailuresCol: "Fail",
    toolLatency: "Tool ms",
    wallClock: "Wall ms",
    wallClockHelp:
      "End-to-end time for that agent's step (LangGraph node or full Copilot run), including LLM and tool calls.",
    sources: "Sources",
    estimatedNote:
      "Some model prices are estimates — actual cost may differ slightly.",
    moaVsBaseline: "MoA vs NBA Copilot cost",
    moaPipeline: "MoA pipeline",
    baselineLlm: "NBA Copilot",
    noSources: "No sources reported by the agents.",
  },
  fr: {
    title: "Métriques du run",
    totalCost: "Coût (USD)",
    totalTokens: "Tokens (in / out)",
    llmCalls: "Appels LLM",
    toolCalls: "Appels d'outils",
    toolFailures: "Échecs d'outils",
    distinctSources: "Sources distinctes",
    duration: "Durée",
    perAgent: "Détail par agent",
    agent: "Agent",
    model: "Modèle",
    llmCallsCol: "LLM",
    inputTokens: "In",
    outputTokens: "Out",
    costUsd: "$",
    llmLatency: "LLM ms",
    toolCallsCol: "Outils",
    toolFailuresCol: "Fails",
    toolLatency: "Outils ms",
    wallClock: "Wall ms",
    wallClockHelp:
      "Temps réel de l'étape de l'agent (nœud LangGraph ou run Copilot complet), LLM et outils inclus.",
    sources: "Sources",
    estimatedNote:
      "Certains prix de modèles sont estimés — le coût réel peut légèrement différer.",
    moaVsBaseline: "Coût MoA vs NBA Copilot",
    moaPipeline: "Pipeline MoA",
    baselineLlm: "NBA Copilot",
    noSources: "Aucune source remontée par les agents.",
  },
};

function fmtCost(usd: number): string {
  if (usd === 0) return "$0";
  if (usd < 0.001) return `$${usd.toExponential(2)}`;
  if (usd < 1) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

function fmtMs(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function fmtTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

export function RunMetricsPanel({
  metrics,
  language,
  compact = false,
}: {
  metrics: RunMetrics;
  language: LanguageCode;
  compact?: boolean;
}) {
  const t = COPY[language];

  const moaRatio = useMemo(() => {
    const total = metrics.moa_cost_usd + metrics.baseline_cost_usd;
    if (total <= 0) return null;
    return {
      moa: metrics.moa_cost_usd / total,
      baseline: metrics.baseline_cost_usd / total,
    };
  }, [metrics.moa_cost_usd, metrics.baseline_cost_usd]);

  return (
    <section className="card space-y-4">
      <header className="flex items-center justify-between gap-3 flex-wrap">
        <h3 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-accent">
          {t.title}
        </h3>
        {metrics.estimated_price && (
          <span
            className="pill border-amber-300 bg-amber-50 text-amber-700"
            title={t.estimatedNote}
          >
            ≈ est.
          </span>
        )}
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 text-sm">
        <Stat label={t.totalCost} value={fmtCost(metrics.total_cost_usd)} highlight />
        <Stat
          label={t.totalTokens}
          value={`${fmtTokens(metrics.total_input_tokens)} / ${fmtTokens(
            metrics.total_output_tokens,
          )}`}
        />
        <Stat label={t.duration} value={fmtMs(metrics.duration_seconds * 1000)} />
        <Stat label={t.llmCalls} value={String(metrics.llm_call_count)} />
        <Stat label={t.toolCalls} value={String(metrics.tool_call_count)} />
        <Stat
          label={t.toolFailures}
          value={String(metrics.tool_failure_count)}
          danger={metrics.tool_failure_count > 0}
        />
        <Stat label={t.distinctSources} value={String(metrics.distinct_sources)} />
      </div>

      {moaRatio && metrics.mode === "compare" && (
        <div>
          <div className="text-xs uppercase tracking-[0.08em] text-muted mb-1">
            {t.moaVsBaseline}
          </div>
          <div
            className="h-4 w-full rounded-full overflow-hidden border border-border bg-slate-50"
            title={`${t.moaPipeline}: ${fmtCost(metrics.moa_cost_usd)} · ${
              t.baselineLlm
            }: ${fmtCost(metrics.baseline_cost_usd)}`}
          >
            <div
              className="h-full bg-amber-400"
              style={{ width: `${Math.round(moaRatio.moa * 100)}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted mt-1">
            <span>
              {t.moaPipeline} {fmtCost(metrics.moa_cost_usd)}
            </span>
            <span>
              {t.baselineLlm} {fmtCost(metrics.baseline_cost_usd)}
            </span>
          </div>
        </div>
      )}

      {!compact && (
        <details className="text-sm" open={metrics.agents.length <= 4}>
          <summary className="cursor-pointer font-semibold text-slate-900">
            {t.perAgent} ({metrics.agents.length})
          </summary>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-muted uppercase tracking-[0.08em]">
                  <th className="py-1 pr-2">{t.agent}</th>
                  <th className="py-1 pr-2">{t.model}</th>
                  <th className="py-1 pr-2 text-right">{t.llmCallsCol}</th>
                  <th className="py-1 pr-2 text-right">{t.inputTokens}</th>
                  <th className="py-1 pr-2 text-right">{t.outputTokens}</th>
                  <th className="py-1 pr-2 text-right">{t.costUsd}</th>
                  <th className="py-1 pr-2 text-right">{t.llmLatency}</th>
                  <th className="py-1 pr-2 text-right">{t.toolCallsCol}</th>
                  <th className="py-1 pr-2 text-right">{t.toolFailuresCol}</th>
                  <th className="py-1 pr-2 text-right">{t.toolLatency}</th>
                  <th className="py-1 pr-2 text-right" title={t.wallClockHelp}>
                    {t.wallClock}
                  </th>
                </tr>
              </thead>
              <tbody>
                {metrics.agents.map((a) => (
                  <tr
                    key={a.agent}
                    className="border-t border-border align-middle"
                  >
                    <td className="py-1 pr-2 font-semibold">{a.agent}</td>
                    <td className="py-1 pr-2 font-mono text-[11px] text-muted truncate max-w-[180px]">
                      {a.model || "—"}
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums">
                      {a.llm_calls || "—"}
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums">
                      {fmtTokens(a.input_tokens)}
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums">
                      {fmtTokens(a.output_tokens)}
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums">
                      {fmtCost(a.cost_usd)}
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums">
                      {fmtMs(a.llm_latency_ms)}
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums">
                      {a.tool_calls || "—"}
                    </td>
                    <td
                      className={clsx(
                        "py-1 pr-2 text-right tabular-nums",
                        a.tool_failures > 0 && "text-red-700 font-semibold",
                      )}
                    >
                      {a.tool_failures || "—"}
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums">
                      {fmtMs(a.tool_latency_ms)}
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums">
                      {fmtMs(a.wall_clock_ms)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {!compact && metrics.sources.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-semibold text-slate-900">
            {t.sources} ({metrics.sources.length})
          </summary>
          <ul className="mt-2 flex flex-wrap gap-2">
            {metrics.sources.map((s) => (
              <li key={s} className="pill text-xs font-mono">
                {s}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function Stat({
  label,
  value,
  highlight,
  danger,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  danger?: boolean;
}) {
  return (
    <div
      className={clsx(
        "rounded-lg border border-border p-2.5 bg-panel",
        highlight && "border-accent/40 bg-amber-50/40",
        danger && "border-red-200 bg-red-50/60",
      )}
    >
      <div className="text-[11px] uppercase tracking-[0.08em] text-muted">
        {label}
      </div>
      <div
        className={clsx(
          "text-lg font-semibold tabular-nums",
          danger && "text-red-700",
          highlight && "text-amber-700",
        )}
      >
        {value}
      </div>
    </div>
  );
}
