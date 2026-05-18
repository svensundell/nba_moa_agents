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

export interface AgentMetrics {
  agent: string;
  model: string;
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  llm_latency_ms: number;
  tool_calls: number;
  tool_failures: number;
  tool_latency_ms: number;
  wall_clock_ms: number;
}

export interface ToolCallMetric {
  agent: string;
  tool: string;
  latency_ms: number;
  success: boolean;
  error: string | null;
  started_at: string;
}

export interface RunMetrics {
  run_id: string;
  mode: "brief" | "query" | "compare";
  started_at: string;
  finished_at: string;
  duration_seconds: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  llm_call_count: number;
  tool_call_count: number;
  tool_failure_count: number;
  distinct_sources: number;
  sources: string[];
  agents: AgentMetrics[];
  tool_calls: ToolCallMetric[];
  moa_cost_usd: number;
  baseline_cost_usd: number;
  estimated_price: boolean;
}

export interface RunSummary {
  run_id: string;
  mode: "brief" | "query" | "compare";
  date: string;
  query: string;
  language: "en" | "fr";
  started_at: string;
  duration_seconds: number;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  llm_call_count: number;
  tool_call_count: number;
  tool_failure_count: number;
  distinct_sources: number;
  moa_cost_usd: number;
  baseline_cost_usd: number;
  estimated_price: boolean;
}

export interface DashboardSummary {
  total_runs: number;
  avg_cost_usd: number;
  avg_duration_seconds: number;
  tool_failure_rate: number;
  cost_by_mode: Record<string, number>;
  avg_cost_by_mode: Record<string, number>;
  runs_by_mode: Record<string, number>;
  compare_avg_moa_cost_usd: number;
  compare_avg_baseline_cost_usd: number;
  p95_duration_seconds: number;
  last_run_at: string | null;
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
  metrics: RunMetrics | null;
}

export interface AgentMeta {
  agent: string;
  logical_model: string;
  provider_model: string;
  description: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export type LanguageCode = "en" | "fr";

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

// ─── Evaluation dashboard ────────────────────────────────────────────────────

export async function fetchRuns(opts?: {
  limit?: number;
  mode?: "brief" | "query" | "compare";
}): Promise<RunSummary[]> {
  const params = new URLSearchParams();
  if (opts?.limit) params.set("limit", String(opts.limit));
  if (opts?.mode) params.set("mode", opts.mode);
  const suffix = params.toString();
  const r = await fetch(`${base}/runs${suffix ? `?${suffix}` : ""}`);
  if (!r.ok) throw new Error(`/runs failed: ${r.status}`);
  return r.json();
}

export async function fetchRunDetail(runId: string): Promise<RunResult> {
  const r = await fetch(`${base}/runs/${encodeURIComponent(runId)}`);
  if (!r.ok) throw new Error(`/runs/${runId} failed: ${r.status}`);
  return r.json();
}

export async function fetchMetricsSummary(lastN = 100): Promise<DashboardSummary> {
  const r = await fetch(`${base}/metrics/summary?last_n=${lastN}`);
  if (!r.ok) throw new Error(`/metrics/summary failed: ${r.status}`);
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
  language: LanguageCode;
  query?: string;
  messages?: ChatMessage[];
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
        language: opts.language,
        query: opts.query ?? "",
        messages: opts.messages ?? [],
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
