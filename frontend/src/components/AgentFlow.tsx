import { useMemo } from "react";
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

export type AgentStatus = "idle" | "running" | "done" | "error";

export interface FlowProps {
  statuses: Record<string, AgentStatus>;
  models: Record<string, string>;
}

const PROPOSERS = ["scores", "news", "stats", "injuries", "social"] as const;
const REFINERS = ["analyst", "narrative"] as const;

const COLOR: Record<AgentStatus, string> = {
  idle: "#1f2530",
  running: "#f59e0b",
  done: "#22c55e",
  error: "#ef4444",
};

function nodeFor(
  id: string,
  label: string,
  layer: string,
  position: { x: number; y: number },
  status: AgentStatus,
  model?: string,
): Node {
  const ring = COLOR[status];
  return {
    id,
    position,
    data: {
      label: (
        <div className="text-left">
          <div className="text-xs uppercase tracking-wide text-muted">{layer}</div>
          <div className="font-semibold text-slate-100 text-sm">{label}</div>
          {model && (
            <div className="text-[10px] font-mono text-muted truncate max-w-[140px]">
              {model}
            </div>
          )}
        </div>
      ),
    },
    style: {
      background: "#11151c",
      border: `2px solid ${ring}`,
      color: "#e2e8f0",
      borderRadius: 12,
      padding: 8,
      width: 170,
      boxShadow: status === "running" ? `0 0 0 6px ${ring}30` : undefined,
      transition: "all 0.25s ease",
    },
  };
}

function buildNodes(
  statuses: Record<string, AgentStatus>,
  models: Record<string, string>,
): Node[] {
  const out: Node[] = [];

  out.push(
    nodeFor("kickoff", "Kickoff", "Layer 0", { x: 60, y: 0 }, statuses.kickoff ?? "idle"),
  );

  PROPOSERS.forEach((p, i) => {
    out.push(
      nodeFor(
        p,
        p[0].toUpperCase() + p.slice(1),
        "Proposer",
        { x: 280, y: i * 90 - 60 },
        statuses[p] ?? "idle",
        models[p],
      ),
    );
  });

  REFINERS.forEach((r, i) => {
    out.push(
      nodeFor(
        r,
        r[0].toUpperCase() + r.slice(1),
        "Refiner",
        { x: 540, y: i * 130 + 30 },
        statuses[r] ?? "idle",
        models[r],
      ),
    );
  });

  out.push(
    nodeFor("editor", "Editor", "Aggregator", { x: 800, y: 110 }, statuses.editor ?? "idle", models.editor),
  );

  return out;
}

function buildEdges(): Edge[] {
  const edges: Edge[] = [];
  PROPOSERS.forEach((p) => {
    edges.push({
      id: `kickoff-${p}`,
      source: "kickoff",
      target: p,
      animated: true,
      style: { stroke: "#1f2530" },
    });
    REFINERS.forEach((r) => {
      edges.push({
        id: `${p}-${r}`,
        source: p,
        target: r,
        style: { stroke: "#1f2530" },
      });
    });
  });
  REFINERS.forEach((r) => {
    edges.push({
      id: `${r}-editor`,
      source: r,
      target: "editor",
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed, color: "#f59e0b" },
      style: { stroke: "#f59e0b" },
    });
  });
  return edges;
}

export function AgentFlow({ statuses, models }: FlowProps) {
  const nodes = useMemo(() => buildNodes(statuses, models), [statuses, models]);
  const edges = useMemo(() => buildEdges(), []);

  return (
    <div className="h-[460px] rounded-xl border border-border bg-panel/40 overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        zoomOnScroll={false}
        panOnScroll={false}
      >
        <Background color="#1f2530" gap={24} />
        <Controls showInteractive={false} className="!bg-panel !border-border" />
      </ReactFlow>
    </div>
  );
}
