import { useEffect, useRef } from "react";
import type { AgentEvent } from "../api";
import clsx from "clsx";

const LAYER_COLOR: Record<string, string> = {
  proposer: "text-amber-300",
  refiner: "text-sky-300",
  aggregator: "text-emerald-300",
  system: "text-slate-400",
};

const TYPE_BADGE: Record<string, string> = {
  tool: "bg-fuchsia-600/20 text-fuchsia-200 border-fuchsia-600/30",
  done: "bg-emerald-600/15 text-emerald-200 border-emerald-600/30",
  error: "bg-red-600/20 text-red-200 border-red-600/40",
  start: "bg-slate-600/20 text-slate-200 border-slate-600/30",
  chunk: "bg-slate-600/10 text-slate-300 border-slate-600/20",
};

export function EventLog({ events }: { events: AgentEvent[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [events.length]);

  return (
    <div
      ref={ref}
      className="card font-mono text-xs h-[460px] overflow-y-auto space-y-1"
    >
      {events.length === 0 && (
        <div className="text-muted italic">Waiting for the agents to start...</div>
      )}
      {events.map((ev, i) => (
        <div key={i} className="flex gap-2 leading-snug">
          <span className="text-muted">
            {new Date(ev.timestamp).toLocaleTimeString()}
          </span>
          <span className={clsx("font-semibold w-20 shrink-0", LAYER_COLOR[ev.layer])}>
            {ev.agent}
          </span>
          <span
            className={clsx(
              "shrink-0 rounded border px-1 text-[10px] uppercase tracking-wide",
              TYPE_BADGE[ev.type] ?? "border-border text-muted",
            )}
          >
            {ev.type}
          </span>
          <span className="text-slate-200 truncate">{ev.content}</span>
        </div>
      ))}
    </div>
  );
}
