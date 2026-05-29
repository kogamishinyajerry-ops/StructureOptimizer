import type { BenchmarkSummary, StartRunResponse } from "./types";

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

export function startRun(benchmark_id: string, preset?: string): Promise<StartRunResponse> {
  return fetch(`${BASE}/api/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ benchmark_id, preset: preset ?? null }),
  }).then(json<StartRunResponse>);
}

/** WebSocket URL for a run's live stream (handles ws/wss + dev proxy). */
export function streamUrl(run_id: string): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/api/runs/${run_id}/stream`;
}
