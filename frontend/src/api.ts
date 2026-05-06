// Tiny API + WebSocket client for the FastAPI backend.

export type Layer = "proposer" | "refiner" | "aggregator" | "system";
export type EventType = "start" | "chunk" | "tool" | "done" | "error";

export interface AgentEvent {
  agent: string;
  layer: Layer;
  type: EventType;
  content: string;
  model: string;
  timestamp: string;
}

export interface ProposalView {
  agent: string;
  model: string;
  summary: string;
  sources: string[];
}

export interface RefinementView {
  agent: string;
  model: string;
  content: string;
}

export interface RunResult {
  mode: "brief" | "query" | "compare";
  date: string;
  query: string;
  final_brief: string;
  single_llm_answer: string;
  proposals: ProposalView[];
  refinements: RefinementView[];
  events: AgentEvent[];
  started_at: string;
  finished_at: string;
  duration_seconds: number;
}

export interface AgentMeta {
  agent: string;
  logical_model: string;
  provider_model: string;
  description: string;
}

const base = "/api";

export async function fetchAgents(): Promise<AgentMeta[]> {
  const r = await fetch(`${base}/agents`);
  if (!r.ok) throw new Error(`/agents failed: ${r.status}`);
  const data = await r.json();
  return data.agents;
}

export interface HealthInfo {
  has_openrouter: boolean;
  has_balldontlie: boolean;
  mcp_initialised: boolean;
  mcp_servers: string[];
  mcp_tools: string[];
}

export async function fetchHealth(): Promise<HealthInfo> {
  const r = await fetch(`${base}/health`);
  return r.json();
}

// ─── WebSocket streaming ─────────────────────────────────────────────────────

export type StreamFrame =
  | { kind: "started"; at: string; mode: string }
  | { kind: "event"; event: AgentEvent }
  | { kind: "node_done"; node: string }
  | { kind: "result"; result: RunResult }
  | { kind: "error"; message: string };

export interface RunOptions {
  mode: "brief" | "query" | "compare";
  query?: string;
  date?: string | null;
  onFrame: (frame: StreamFrame) => void;
}

export function streamRun(opts: RunOptions): { close: () => void } {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${window.location.host}${base}/ws/run`;
  const ws = new WebSocket(url);

  ws.onopen = () => {
    ws.send(
      JSON.stringify({
        mode: opts.mode,
        query: opts.query ?? "",
        date: opts.date ?? null,
      }),
    );
  };

  ws.onmessage = (e) => {
    try {
      const frame: StreamFrame = JSON.parse(e.data);
      opts.onFrame(frame);
    } catch (err) {
      console.error("bad frame", err, e.data);
    }
  };

  ws.onerror = (e) => {
    console.error("websocket error", e);
    opts.onFrame({ kind: "error", message: "WebSocket error" });
  };

  return {
    close: () => {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
    },
  };
}
