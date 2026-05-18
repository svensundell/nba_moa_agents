import { useCallback, useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import {
  EMPTY_DASHBOARD_SUMMARY,
  fetchMetricsSummary,
  fetchRunDetail,
  fetchRuns,
  type DashboardSummary,
  type LanguageCode,
  type RunResult,
  type RunSummary,
} from "../api";
import { RunMetricsPanel } from "./RunMetricsPanel";
import { Markdown } from "./Markdown";

type T = {
  title: string;
  intro: string;
  refresh: string;
  loading: string;
  empty: string;
  emptyFiltered: string;
  modeAll: string;
  modeBrief: string;
  modeQuery: string;
  modeCompare: string;
  filterByMode: string;
  summary: string;
  totalRuns: string;
  avgCost: string;
  avgDuration: string;
  p95Duration: string;
  toolFailureRate: string;
  compareSection: string;
  compareMoa: string;
  compareBaseline: string;
  costByModeTitle: string;
  costPerRunTitle: string;
  latencyByAgentTitle: string;
  runsTableTitle: string;
  colDate: string;
  colMode: string;
  colQuery: string;
  colDuration: string;
  colCost: string;
  colTokens: string;
  colLlm: string;
  colTools: string;
  colFails: string;
  colSources: string;
  noRunDetail: string;
  selectedRun: string;
  closeDetail: string;
  brief: string;
  baselineHeading: string;
  noDataChart: string;
  warningPartial: string;
  backendUnreachable: string;
};

const COPY: Record<LanguageCode, T> = {
  en: {
    title: "Evaluation Dashboard",
    intro:
      "Observe every pipeline run's cost, latency, tool reliability and source coverage over time. Persisted to SQLite under data/eval.db.",
    refresh: "Refresh",
    loading: "Loading metrics…",
    empty: "No runs yet — run a Brief or query NBA Copilot to populate the dashboard.",
    emptyFiltered:
      "No runs recorded for « {mode} ». Launch a pipeline in that tab, then refresh.",
    modeAll: "All modes",
    modeBrief: "Brief",
    modeQuery: "Copilot",
    modeCompare: "Compare",
    filterByMode: "Filter",
    summary: "Last 100 runs",
    totalRuns: "Runs",
    avgCost: "Avg cost",
    avgDuration: "Avg duration",
    p95Duration: "p95 duration",
    toolFailureRate: "Tool failure rate",
    compareSection: "Compare mode",
    compareMoa: "Avg MoA cost",
    compareBaseline: "Avg single-agent cost",
    costByModeTitle: "Total cost by mode",
    costPerRunTitle: "Cost per run (recent → past)",
    latencyByAgentTitle: "Avg LLM latency per agent (selected run)",
    runsTableTitle: "Run history",
    colDate: "Date",
    colMode: "Mode",
    colQuery: "Query",
    colDuration: "Duration",
    colCost: "Cost",
    colTokens: "Tokens",
    colLlm: "LLM",
    colTools: "Tools",
    colFails: "Fails",
    colSources: "Srcs",
    noRunDetail: "Select a run in the table to inspect its full payload.",
    selectedRun: "Selected run",
    closeDetail: "Close",
    brief: "Final brief",
    baselineHeading: "Single-agent baseline",
    noDataChart: "No data yet.",
    warningPartial: "Some metrics could not be loaded:",
    backendUnreachable:
      "Cannot reach the API. Start the backend on port 8000, then click Refresh.",
  },
  fr: {
    title: "Tableau de bord d'évaluation",
    intro:
      "Mesurez le coût, la latence, la fiabilité des outils et la couverture des sources de chaque run. Persisté dans SQLite (data/eval.db).",
    refresh: "Rafraîchir",
    loading: "Chargement des métriques…",
    empty:
      "Aucun run enregistré — lancez un Brief ou interrogez NBA Copilot pour alimenter le tableau.",
    emptyFiltered:
      "Aucun run pour « {mode} ». Lancez le pipeline dans cet onglet, puis rafraîchissez.",
    modeAll: "Tous les modes",
    modeBrief: "Brief",
    modeQuery: "Copilot",
    modeCompare: "Compare",
    filterByMode: "Filtrer",
    summary: "100 derniers runs",
    totalRuns: "Runs",
    avgCost: "Coût moyen",
    avgDuration: "Durée moyenne",
    p95Duration: "p95 durée",
    toolFailureRate: "Taux d'échec d'outils",
    compareSection: "Mode comparaison",
    compareMoa: "Coût MoA moyen",
    compareBaseline: "Coût agent unique moyen",
    costByModeTitle: "Coût total par mode",
    costPerRunTitle: "Coût par run (récent → ancien)",
    latencyByAgentTitle: "Latence LLM moyenne par agent (run sélectionné)",
    runsTableTitle: "Historique des runs",
    colDate: "Date",
    colMode: "Mode",
    colQuery: "Question",
    colDuration: "Durée",
    colCost: "Coût",
    colTokens: "Tokens",
    colLlm: "LLM",
    colTools: "Outils",
    colFails: "Fails",
    colSources: "Srcs",
    noRunDetail:
      "Sélectionnez un run dans le tableau pour inspecter son payload complet.",
    selectedRun: "Run sélectionné",
    closeDetail: "Fermer",
    brief: "Brief final",
    baselineHeading: "Baseline agent unique",
    noDataChart: "Pas encore de donnée.",
    warningPartial: "Certaines métriques n'ont pas pu être chargées :",
    backendUnreachable:
      "API injoignable. Démarre le backend sur le port 8000, puis clique sur Rafraîchir.",
  },
};

type ModeFilter = "all" | "brief" | "query" | "compare";

function fmtCost(usd: number): string {
  if (!usd) return "$0";
  if (usd < 0.001) return `$${usd.toExponential(2)}`;
  if (usd < 1) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

function fmtMs(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function fmtSeconds(s: number): string {
  if (!Number.isFinite(s) || s <= 0) return "—";
  return `${s.toFixed(2)} s`;
}

function fmtTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

function fmtPct(x: number): string {
  return `${(x * 100).toFixed(1)}%`;
}

export function EvalDashboard({ language }: { language: LanguageCode }) {
  const t = COPY[language];
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<ModeFilter>("all");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<RunResult | null>(null);
  const [selectedLoading, setSelectedLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    setWarning(null);
    const modeFilter = mode === "all" ? undefined : mode;
    const [summarySettled, runsSettled] = await Promise.allSettled([
      fetchMetricsSummary({ lastN: 100, mode: modeFilter }),
      fetchRuns({ limit: 50, mode: modeFilter }),
    ]);

    const summaryOk = summarySettled.status === "fulfilled";
    const runsOk = runsSettled.status === "fulfilled";

    if (summaryOk) {
      setSummary(summarySettled.value);
    } else {
      setSummary(EMPTY_DASHBOARD_SUMMARY);
    }

    if (runsOk) {
      setRuns(runsSettled.value);
    } else {
      setRuns([]);
    }

    const partialErrors: string[] = [];
    if (!summaryOk) {
      partialErrors.push((summarySettled.reason as Error).message);
    }
    if (!runsOk) {
      partialErrors.push((runsSettled.reason as Error).message);
    }

    if (!summaryOk && !runsOk) {
      setError(
        partialErrors.join(" ") ||
          t.backendUnreachable,
      );
    } else if (partialErrors.length > 0) {
      setWarning(`${t.warningPartial} ${partialErrors.join(" ")}`);
    }

    setLoading(false);
  }, [mode, t.backendUnreachable, t.warningPartial]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRun(null);
      return;
    }
    setSelectedLoading(true);
    fetchRunDetail(selectedRunId)
      .then(setSelectedRun)
      .catch((err) => setError((err as Error).message))
      .finally(() => setSelectedLoading(false));
  }, [selectedRunId]);

  const costSeries = useMemo(
    () => runs.map((r) => ({ label: r.run_id.slice(0, 6), value: r.total_cost_usd })),
    [runs],
  );

  const costByMode = useMemo(() => {
    if (!summary) return [];
    return Object.entries(summary.cost_by_mode ?? {}).map(([m, v]) => ({
      label: modeDisplayLabel(m, t),
      value: v,
    }));
  }, [summary, t]);

  const latencyByAgent = useMemo(() => {
    if (!selectedRun?.metrics) return [];
    return selectedRun.metrics.agents
      .filter((a) => a.llm_calls > 0)
      .map((a) => ({
        label: a.agent,
        value: a.llm_calls > 0 ? a.llm_latency_ms / a.llm_calls : 0,
      }));
  }, [selectedRun]);

  return (
    <section className="space-y-6">
      <header className="card flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">{t.title}</h2>
          <p className="text-sm text-muted mt-1">{t.intro}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            className="input py-2 max-w-[160px]"
            value={mode}
            onChange={(e) => setMode(e.target.value as ModeFilter)}
            aria-label={t.filterByMode}
          >
            <option value="all">{t.modeAll}</option>
            <option value="brief">{t.modeBrief}</option>
            <option value="query">{t.modeQuery}</option>
            <option value="compare">{t.modeCompare}</option>
          </select>
          <button
            className="btn-secondary"
            onClick={() => void refresh()}
            disabled={loading}
            type="button"
          >
            {loading ? t.loading : t.refresh}
          </button>
        </div>
      </header>

      {error && (
        <div className="card border-red-300 bg-red-50 text-red-700 text-sm">
          {error}
        </div>
      )}

      {warning && !error && (
        <div className="card border-amber-300 bg-amber-50 text-amber-800 text-sm">
          {warning}
        </div>
      )}

      {summary && summary.total_runs === 0 && !loading && !error && (
        <div className="card text-base text-muted italic">
          {mode === "all"
            ? t.empty
            : t.emptyFiltered.replace("{mode}", modeDisplayLabel(mode, t))}
        </div>
      )}

      {summary && summary.total_runs > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <SummaryStat label={t.totalRuns} value={String(summary.total_runs)} />
          <SummaryStat label={t.avgCost} value={fmtCost(summary.avg_cost_usd)} highlight />
          <SummaryStat
            label={t.avgDuration}
            value={fmtSeconds(summary.avg_duration_seconds)}
          />
          <SummaryStat
            label={t.p95Duration}
            value={fmtSeconds(summary.p95_duration_seconds)}
          />
          <SummaryStat
            label={t.toolFailureRate}
            value={fmtPct(summary.tool_failure_rate)}
            danger={summary.tool_failure_rate > 0.05}
          />
        </div>
      )}

      {summary &&
        (mode === "all" || mode === "compare") &&
        (summary.compare_avg_moa_cost_usd > 0 ||
          summary.compare_avg_baseline_cost_usd > 0) && (
          <section className="card space-y-3">
            <h3 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted">
              {t.compareSection}
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <SummaryStat
                label={t.compareMoa}
                value={fmtCost(summary.compare_avg_moa_cost_usd)}
                highlight
              />
              <SummaryStat
                label={t.compareBaseline}
                value={fmtCost(summary.compare_avg_baseline_cost_usd)}
              />
            </div>
          </section>
        )}

      <div className="grid gap-4 lg:grid-cols-2">
        <BarChartCard
          title={t.costPerRunTitle}
          emptyLabel={t.noDataChart}
          data={costSeries}
          format={fmtCost}
          accent="bg-amber-400"
        />
        <BarChartCard
          title={t.costByModeTitle}
          emptyLabel={t.noDataChart}
          data={costByMode}
          format={fmtCost}
          accent="bg-sky-400"
        />
      </div>

      <section className="card space-y-3">
        <h3 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted">
          {t.runsTableTitle}
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="text-muted uppercase tracking-[0.08em] text-xs">
                <th className="py-2 pr-2">{t.colDate}</th>
                <th className="py-2 pr-2">{t.colMode}</th>
                <th className="py-2 pr-2">{t.colQuery}</th>
                <th className="py-2 pr-2 text-right">{t.colDuration}</th>
                <th className="py-2 pr-2 text-right">{t.colCost}</th>
                <th className="py-2 pr-2 text-right">{t.colTokens}</th>
                <th className="py-2 pr-2 text-right">{t.colLlm}</th>
                <th className="py-2 pr-2 text-right">{t.colTools}</th>
                <th className="py-2 pr-2 text-right">{t.colFails}</th>
                <th className="py-2 pr-2 text-right">{t.colSources}</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr
                  key={r.run_id}
                  className={clsx(
                    "border-t border-border cursor-pointer hover:bg-amber-50/40",
                    selectedRunId === r.run_id && "bg-amber-50",
                  )}
                  onClick={() => setSelectedRunId(r.run_id)}
                >
                  <td className="py-2 pr-2 font-mono text-xs">
                    {new Date(r.started_at).toLocaleString(language === "fr" ? "fr-FR" : "en-US")}
                  </td>
                  <td className="py-2 pr-2">
                    <ModePill mode={r.mode} label={modeDisplayLabel(r.mode, t)} />
                  </td>
                  <td className="py-2 pr-2 max-w-[260px] truncate" title={r.query}>
                    {r.query || (r.mode === "brief" ? "Daily Brief" : "—")}
                  </td>
                  <td className="py-2 pr-2 text-right tabular-nums">
                    {fmtSeconds(r.duration_seconds)}
                  </td>
                  <td className="py-2 pr-2 text-right tabular-nums">
                    {fmtCost(r.total_cost_usd)}
                  </td>
                  <td className="py-2 pr-2 text-right tabular-nums">
                    {fmtTokens(r.total_input_tokens + r.total_output_tokens)}
                  </td>
                  <td className="py-2 pr-2 text-right tabular-nums">{r.llm_call_count}</td>
                  <td className="py-2 pr-2 text-right tabular-nums">{r.tool_call_count}</td>
                  <td
                    className={clsx(
                      "py-2 pr-2 text-right tabular-nums",
                      r.tool_failure_count > 0 && "text-red-700 font-semibold",
                    )}
                  >
                    {r.tool_failure_count}
                  </td>
                  <td className="py-2 pr-2 text-right tabular-nums">
                    {r.distinct_sources}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {runs.length === 0 && !loading && (
            <p className="text-sm text-muted italic py-4 text-center">{t.empty}</p>
          )}
        </div>
      </section>

      {selectedRunId && (
        <section className="card space-y-4">
          <header className="flex items-center justify-between">
            <h3 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted">
              {t.selectedRun} ·{" "}
              <span className="font-mono">{selectedRunId.slice(0, 12)}</span>
            </h3>
            <button
              className="btn-secondary"
              type="button"
              onClick={() => setSelectedRunId(null)}
            >
              {t.closeDetail}
            </button>
          </header>

          {selectedLoading && (
            <p className="text-sm text-muted italic">{t.loading}</p>
          )}

          {selectedRun?.metrics && (
            <>
              <RunMetricsPanel metrics={selectedRun.metrics} language={language} />

              <BarChartCard
                title={t.latencyByAgentTitle}
                emptyLabel={t.noDataChart}
                data={latencyByAgent}
                format={(v) => fmtMs(v)}
                accent="bg-emerald-400"
              />

              {selectedRun.final_brief && (
                <details className="text-sm" open>
                  <summary className="cursor-pointer font-semibold text-slate-900 mb-2">
                    {t.brief}
                  </summary>
                  <div className="mt-2 prose-brief">
                    <Markdown content={selectedRun.final_brief} />
                  </div>
                </details>
              )}

              {selectedRun.single_llm_answer && (
                <details className="text-sm">
                  <summary className="cursor-pointer font-semibold text-slate-900 mb-2">
                    {t.baselineHeading}
                  </summary>
                  <div className="mt-2 prose-brief">
                    <Markdown content={selectedRun.single_llm_answer} />
                  </div>
                </details>
              )}
            </>
          )}
        </section>
      )}

      {!selectedRunId && runs.length > 0 && (
        <p className="text-sm text-muted italic">{t.noRunDetail}</p>
      )}
    </section>
  );
}

function SummaryStat({
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
        "rounded-xl border border-border p-3 bg-panel",
        highlight && "border-accent/40 bg-amber-50/40",
        danger && "border-red-200 bg-red-50/60",
      )}
    >
      <div className="text-[11px] uppercase tracking-[0.08em] text-muted">
        {label}
      </div>
      <div
        className={clsx(
          "text-xl font-semibold tabular-nums",
          danger && "text-red-700",
          highlight && "text-amber-700",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function modeDisplayLabel(mode: string, t: T): string {
  if (mode === "brief") return t.modeBrief;
  if (mode === "query") return t.modeQuery;
  if (mode === "compare") return t.modeCompare;
  return mode;
}

function ModePill({
  mode,
  label,
}: {
  mode: "brief" | "query" | "compare";
  label: string;
}) {
  const c =
    mode === "brief"
      ? "border-emerald-300 bg-emerald-50 text-emerald-700"
      : mode === "query"
        ? "border-sky-300 bg-sky-50 text-sky-700"
        : "border-amber-300 bg-amber-50 text-amber-700";
  return <span className={clsx("pill text-xs", c)}>{label}</span>;
}

/**
 * Minimal SVG bar chart. Re-implemented locally rather than pulling in a
 * dependency because the only thing we need is bars with labels — the
 * `recharts` payload is two orders of magnitude bigger and the eval
 * dashboard never has more than ~50 bars.
 */
function BarChartCard({
  title,
  data,
  format,
  accent,
  emptyLabel,
}: {
  title: string;
  data: { label: string; value: number }[];
  format: (v: number) => string;
  accent: string;
  emptyLabel: string;
}) {
  const max = data.length > 0 ? Math.max(...data.map((d) => d.value), 0) : 0;
  return (
    <div className="card">
      <h4 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted mb-3">
        {title}
      </h4>
      {data.length === 0 ? (
        <p className="text-sm text-muted italic">{emptyLabel}</p>
      ) : (
        <div className="space-y-2">
          {data.map((d, idx) => {
            const pct = max > 0 ? (d.value / max) * 100 : 0;
            return (
              <div key={`${d.label}-${idx}`} className="flex items-center gap-2">
                <span className="w-24 text-xs font-mono truncate text-muted">
                  {d.label}
                </span>
                <div className="flex-1 h-3 rounded-full bg-slate-100 overflow-hidden border border-border">
                  <div
                    className={clsx("h-full", accent)}
                    style={{ width: `${Math.max(2, pct)}%` }}
                  />
                </div>
                <span className="w-20 text-right text-xs tabular-nums text-slate-700">
                  {format(d.value)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
