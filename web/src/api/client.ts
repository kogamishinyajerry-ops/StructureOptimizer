import type {
  BenchmarkConfigEditable,
  BenchmarkSummary,
  RunDetail,
  RunListItem,
  RunOverrides,
  StageRecord,
  StartRunResponse,
} from "./types";

const BASE = ""; // same-origin; Vite proxies /api to the backend in dev.

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function fetchBenchmarks(): Promise<BenchmarkSummary[]> {
  return fetch(`${BASE}/api/benchmarks`).then(json<BenchmarkSummary[]>);
}

export function fetchBenchmarkConfig(id: string): Promise<BenchmarkConfigEditable> {
  return fetch(`${BASE}/api/benchmarks/${id}/config`).then(json<BenchmarkConfigEditable>);
}

export function startRun(
  benchmark_id: string,
  preset?: string,
  overrides?: RunOverrides,
): Promise<StartRunResponse> {
  return fetch(`${BASE}/api/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ benchmark_id, preset: preset ?? null, ...(overrides ? { overrides } : {}) }),
  }).then(json<StartRunResponse>);
}

/** Past runs, newest first, for the history panel. */
export function fetchRuns(): Promise<RunListItem[]> {
  return fetch(`${BASE}/api/runs`).then(json<RunListItem[]>);
}

/** Full payload (summary + verification + metrics + density) for one run. */
export function fetchRun(run_id: string): Promise<RunDetail> {
  return fetch(`${BASE}/api/runs/${run_id}`).then(json<RunDetail>);
}

/** The run's per-stage agent-rail records (agents_trace.json), for history replay. */
export function fetchTrace(run_id: string): Promise<StageRecord[]> {
  return fetch(`${BASE}/api/runs/${run_id}/trace`).then(json<StageRecord[]>);
}

export type RunProbe =
  | { state: "done"; detail: RunDetail }
  | { state: "running" }
  | { state: "errored"; message: string }
  | { state: "missing" };

/**
 * Probe a run's terminal state WITHOUT throwing on the expected non-2xx codes,
 * so the disconnect-recovery poller can branch cleanly: 200 -> done, 409 -> still
 * running, 500 -> errored, 404 -> missing. (``fetchRun`` throws a generic Error
 * with the status baked into the message string, which is awkward to branch on.)
 */
export async function probeRun(run_id: string): Promise<RunProbe> {
  const res = await fetch(`${BASE}/api/runs/${run_id}`);
  if (res.ok) return { state: "done", detail: (await res.json()) as RunDetail };
  if (res.status === 404) return { state: "missing" };
  if (res.status === 409) {
    // get_run returns 409 for TWO distinct states: "Run not finished" (still
    // running -> keep polling) and "Run artifacts are incomplete" (a finished-
    // but-corrupt run — a TERMINAL error that must surface immediately, not poll
    // for 9s then time out into a generic connection-loss message).
    const body = await res.text().catch(() => "");
    let detail = body;
    try {
      detail = (JSON.parse(body) as { detail?: string }).detail ?? body;
    } catch {
      /* non-JSON body — keep raw */
    }
    if (/not finished/i.test(detail)) return { state: "running" };
    return { state: "errored", message: detail || "Run artifacts are incomplete" };
  }
  const message = await res.text().catch(() => res.statusText);
  return { state: "errored", message };
}

/** WebSocket URL for a run's live stream (handles ws/wss + dev proxy). */
export function streamUrl(run_id: string): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/api/runs/${run_id}/stream`;
}

export type ExportFormat = "svg" | "dxf" | "stl";

/** Download a run's optimized geometry. Triggers a browser file download. */
export async function downloadExport(run_id: string, format: ExportFormat): Promise<void> {
  const res = await fetch(`${BASE}/api/runs/${run_id}/export?format=${format}`);
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") ?? "";
  const match = cd.match(/filename="([^"]+)"/);
  const filename = match?.[1] ?? `geometry.${format}`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
