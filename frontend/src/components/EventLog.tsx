import { useEffect, useRef } from "react";
import type { AgentEvent, LanguageCode } from "../api";
import clsx from "clsx";

const LAYER_COLOR: Record<string, string> = {
  proposer: "text-amber-700",
  refiner: "text-sky-700",
  aggregator: "text-emerald-700",
  system: "text-slate-500",
};

const TYPE_BADGE: Record<string, string> = {
  tool: "bg-amber-50 text-amber-700 border-amber-200",
  done: "bg-emerald-50 text-emerald-700 border-emerald-200",
  error: "bg-red-50 text-red-700 border-red-200",
  start: "bg-slate-100 text-slate-700 border-slate-200",
  chunk: "bg-slate-50 text-slate-600 border-slate-200",
};

export function EventLog({ events, language }: { events: AgentEvent[]; language?: LanguageCode }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [events.length]);

  return (
    <div
      ref={ref}
      className="card font-mono text-sm max-h-80 overflow-y-auto space-y-1.5"
    >
      {events.length === 0 && (
        <div className="text-muted italic text-base">Waiting for the agents to start...</div>
      )}
      {events.map((ev, i) => (
        <div key={i} className="grid gap-1 sm:gap-2 sm:grid-cols-[auto_auto_auto_1fr] leading-snug py-1 border-b border-border">
          <span className="text-muted">
            {new Date(ev.timestamp).toLocaleTimeString(language)}
          </span>
          <span className={clsx("font-semibold w-24 shrink-0", LAYER_COLOR[ev.layer])}>
            {ev.agent}
          </span>
          <span
            className={clsx(
              "shrink-0 rounded border px-1.5 py-0.5 text-xs uppercase tracking-wide",
              TYPE_BADGE[ev.type] ?? "border-border text-muted",
            )}
          >
            {ev.type}
          </span>
          <span className="text-slate-700 break-words min-w-0 text-sm">{ev.content}</span>
        </div>
      ))}
    </div>
  );
}
