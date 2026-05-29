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

export interface IterationFrame {
  type: "iteration";
  iteration: number;
  compliance: number;
  volume_fraction: number;
  change: number;
  max_displacement: number;
  mass: number;
  shape: [number, number]; // [nely, nelx]
  density_b64: string;
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

export type StreamFrame = IterationFrame | DoneFrame | ErrorFrame;

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
