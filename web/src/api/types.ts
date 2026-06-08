// Mirrors server/schemas.py one-to-one. Keep in sync with the backend contract.

export interface BenchmarkSummary {
  id: string;
  label: string;
  nelx: number;
  nely: number;
  volume_fraction: number;
  max_iterations: number;
  presets: string[];
  description: string | null;
  recommended: boolean;
}

export interface StartRunResponse {
  run_id: string;
  benchmark_id: string;
  nelx: number;
  nely: number;
}

/** One convergence-curve sample (shared by live frames and persisted metrics). */
export interface MetricPoint {
  iteration: number;
  compliance: number;
  volume_fraction: number;
  change: number;
  max_displacement: number;
  mass: number;
}

export interface IterationFrame extends MetricPoint {
  type: "iteration";
  shape: [number, number]; // [nely, nelx]
  density_b64: string;
}

/** Summary row for the run-history list (GET /api/runs). */
export interface RunListItem {
  run_id: string;
  benchmark_id: string;
  label: string;
  nelx: number;
  nely: number;
  status: string;
  compliance: number | null;
  verified: boolean | null;
  iterations: number | null;
}

/** Full payload for reopening a completed run (GET /api/runs/{run_id}). */
export interface RunDetail {
  run_id: string;
  benchmark_id: string;
  status: string;
  summary: Record<string, unknown>;
  verification: Record<string, unknown>;
  shape: [number, number];
  density_b64: string;
  metrics: MetricPoint[];
}

export interface DoneFrame {
  type: "done";
  run_id: string;
  iterations: number;
  stop_reason: string;
  summary: Record<string, unknown>;
  verification: Record<string, unknown>;
  shape: [number, number];
  density_b64: string;
}

export interface ErrorFrame {
  type: "error";
  message: string;
}

/** A pipeline stage's gate verdict (mirrors server StageGate / pipeline.GateVerdict). */
export interface StageGate {
  name: string;
  ok: boolean;
  verdict_status: string;
  detail: string;
}

/** One agents_trace.json entry — the orchestrator-measured stage result. */
export interface StageRecord {
  name: string;
  role: string;
  tool: string;
  declared_tools: string[];
  domain_agent: boolean;
  status: string;
  gate: StageGate;
  artifacts: string[];
  detail: Record<string, unknown>;
  wall_ms: number;
}

/**
 * Per-stage agent-rail event. `record` is present for `end`/`error` (the trace
 * record) and null for `start` (active marker only). Metadata only — the live
 * density never rides this frame (it flows via IterationFrame).
 */
export interface StageFrame {
  type: "stage";
  phase: "start" | "end" | "error";
  agent: string;
  record: StageRecord | null;
}

export type StreamFrame = IterationFrame | DoneFrame | ErrorFrame | StageFrame;

// ---- M3: problem-definition editor (mirrors server/overrides.py contract) ----

export interface EditableLoad {
  selector: string;
  fx: number;
  fy: number;
}

export interface BenchmarkConfigEditable {
  benchmark_id: string;
  optimization: {
    volume_fraction: number;
    penalty: number;
    filter_radius: number;
    max_iterations: number;
  };
  mesh: { nelx: number; nely: number };
  loads: EditableLoad[];
  loads_editable: boolean;
  selectors: string[];
  limits: {
    nelx_max: number;
    nely_max: number;
    elements_max: number;
    max_iterations_max: number;
  };
}

export interface RunOverrides {
  optimization?: {
    volume_fraction: number;
    penalty: number;
    filter_radius: number;
    max_iterations: number;
  };
  mesh?: { nelx: number; nely: number };
  loads?: EditableLoad[];
}

/** Decode a base64 uint8 density payload into a Float32Array in [0,1]. */
export function decodeDensity(b64: string): Float32Array {
  const bin = atob(b64);
  const out = new Float32Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i) / 255;
  return out;
}
