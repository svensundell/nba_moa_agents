import clsx from "clsx";
import type { LanguageCode, SourceCitation } from "../api";

const COPY = {
  en: {
    title: "Sources",
    intro: "Data providers, MCP tools and retrieval timestamps for this run.",
    agent: "Agent",
    retrieved: "Retrieved",
    excerpt: "Excerpt",
    open: "Open",
    clickHint: "Click a [n] reference in the answer to highlight the matching source.",
    showInTrace: "Show in trace",
  },
  fr: {
    title: "Sources",
    intro:
      "Fournisseurs, outils MCP et horodatages de récupération pour ce run.",
    agent: "Agent",
    retrieved: "Récupéré",
    excerpt: "Extrait",
    open: "Ouvrir",
    clickHint:
      "Cliquez sur une référence [n] dans la réponse pour surligner la source.",
    showInTrace: "Voir dans la trace",
  },
} as const;

function providerClass(provider: string): string {
  const p = provider.toLowerCase();
  if (p.includes("espn")) return "border-orange-300 bg-orange-50 text-orange-800";
  if (p.includes("reddit")) return "border-violet-300 bg-violet-50 text-violet-800";
  if (p.includes("balldontlie") || p.includes("nba"))
    return "border-emerald-300 bg-emerald-50 text-emerald-800";
  return "border-slate-300 bg-slate-50 text-slate-700";
}

export function SourcesBibliography({
  citations,
  language,
  activeId,
  onSelect,
  showHint = true,
}: {
  citations: SourceCitation[];
  language: LanguageCode;
  activeId?: number | null;
  onSelect?: (id: number) => void;
  showHint?: boolean;
}) {
  const t = COPY[language];
  if (citations.length === 0) return null;

  return (
    <section className="card space-y-3" id="sources-section">
      <div>
        <h3 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted">
          {t.title} ({citations.length})
        </h3>
        <p className="text-sm text-muted mt-1">{t.intro}</p>
        {showHint && onSelect && (
          <p className="text-xs text-muted mt-1 italic">{t.clickHint}</p>
        )}
      </div>

      <ol className="space-y-3 list-none m-0 p-0">
        {citations.map((c) => (
          <li
            key={c.id}
            id={`source-${c.id}`}
            className={clsx(
              "rounded-lg border p-3 transition-colors",
              activeId === c.id
                ? "border-accent bg-amber-50/80 ring-2 ring-accent/30"
                : "border-border bg-panel",
            )}
          >
            <div className="flex flex-wrap items-start gap-2 justify-between">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm font-semibold text-accent">[{c.id}]</span>
                <span className={clsx("pill text-xs", providerClass(c.provider))}>
                  {c.provider}
                </span>
                <span className="text-xs font-mono text-muted">{c.tool}</span>
              </div>
              {c.url && (
                <a
                  href={c.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-sky-700 hover:underline shrink-0"
                >
                  {t.open} ↗
                </a>
              )}
            </div>
            <p className="text-sm font-medium text-slate-900 mt-2">{c.title}</p>
            <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 mt-2 text-xs text-muted">
              <div>
                <dt className="uppercase tracking-wide">{t.agent}</dt>
                <dd className="text-slate-800 font-mono">{c.agent}</dd>
              </div>
              <div>
                <dt className="uppercase tracking-wide">{t.retrieved}</dt>
                <dd className="text-slate-800">
                  {new Date(c.retrieved_at).toLocaleString()}
                </dd>
              </div>
            </dl>
            {c.excerpt && (
              <p className="text-xs text-slate-600 mt-2 whitespace-pre-wrap border-t border-border pt-2">
                <span className="font-semibold text-muted">{t.excerpt}: </span>
                {c.excerpt}
              </p>
            )}
            {onSelect && (
              <button
                type="button"
                className="mt-2 text-xs text-accent hover:underline"
                onClick={() => onSelect(c.id)}
              >
                {t.showInTrace}
              </button>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
