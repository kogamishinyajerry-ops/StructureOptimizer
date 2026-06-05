import { useCallback, useEffect, useRef, useState } from "react";
import { fetchRun, startRun, streamUrl } from "./client";
import type { DoneFrame, MetricPoint, RunOverrides, StageFrame, StreamFrame } from "./types";

export type RunStatus = "idle" | "starting" | "running" | "done" | "error";

export interface RunSnapshot {
  status: RunStatus;
  runId: string | null;
  benchmarkId: string | null;
  shape: [number, number] | null; // [nely, nelx]
  /** Latest density frame (base64 uint8), updated per iteration. */
  density: string | null;
  iterations: MetricPoint[];
  /** Ordered per-stage agent-rail events (start/end/error) for the live pipeline. */
  stages: StageFrame[];
  done: DoneFrame | null;
  error: string | null;
}

const EMPTY: RunSnapshot = {
  status: "idle",
  runId: null,
  benchmarkId: null,
  shape: null,
  density: null,
  iterations: [],
  stages: [],
  done: null,
  error: null,
};

/**
 * Drives one optimization run: POST /api/runs, then consume the WS stream,
 * accumulating iteration frames and exposing the latest density for the
 * viewport. Re-running cleanly tears down any prior socket.
 */
function detach(ws: WebSocket | null): void {
  if (!ws) return;
  ws.onmessage = null;
  ws.onerror = null;
  ws.onclose = null;
  ws.close();
}

export function useRun() {
  const [snap, setSnap] = useState<RunSnapshot>(EMPTY);
  const wsRef = useRef<WebSocket | null>(null);

  // Close any live socket when the hook unmounts (prevents leaks + setState-on-unmounted).
  useEffect(() => () => detach(wsRef.current), []);

  const reset = useCallback(() => {
    detach(wsRef.current);
    wsRef.current = null;
    setSnap(EMPTY);
  }, []);

  const launch = useCallback(async (benchmarkId: string, preset?: string, overrides?: RunOverrides) => {
    detach(wsRef.current);
    wsRef.current = null;
    setSnap({ ...EMPTY, status: "starting", benchmarkId });
    let start;
    try {
      start = await startRun(benchmarkId, preset, overrides);
    } catch (e) {
      setSnap({ ...EMPTY, status: "error", benchmarkId, error: (e as Error).message });
      return;
    }

    const shape: [number, number] = [start.nely, start.nelx];
    setSnap({ ...EMPTY, status: "running", runId: start.run_id, benchmarkId, shape });

    const ws = new WebSocket(streamUrl(start.run_id));
    wsRef.current = ws;

    // Guard every handler: a frame queued on a superseded socket must not mutate
    // the new run's state (fast re-run race).
    ws.onmessage = (ev) => {
      if (wsRef.current !== ws) return;
      const frame = JSON.parse(ev.data) as StreamFrame;
      setSnap((prev) => {
        if (frame.type === "iteration") {
          return {
            ...prev,
            status: "running",
            density: frame.density_b64,
            shape: frame.shape,
            iterations: [...prev.iterations, frame],
          };
        }
        if (frame.type === "done") {
          return {
            ...prev,
            status: "done",
            density: frame.density_b64,
            shape: frame.shape,
            done: frame,
          };
        }
        if (frame.type === "stage") {
          return { ...prev, stages: [...prev.stages, frame] };
        }
        return { ...prev, status: "error", error: frame.message };
      });
    };

    ws.onerror = () => {
      if (wsRef.current !== ws) return;
      setSnap((prev) =>
        prev.status === "done" ? prev : { ...prev, status: "error", error: "Connection lost" },
      );
    };

    // A clean close without a terminal frame would otherwise hang the UI on "running".
    ws.onclose = () => {
      if (wsRef.current !== ws) return;
      setSnap((prev) =>
        prev.status === "running" || prev.status === "starting"
          ? { ...prev, status: "error", error: "Connection closed" }
          : prev,
      );
    };
  }, []);

  // Reopen a finished run from history: drop any live socket, fetch the
  // persisted detail, and rebuild a terminal "done" snapshot (no streaming).
  const loadRun = useCallback(async (runId: string) => {
    detach(wsRef.current);
    wsRef.current = null;
    setSnap({ ...EMPTY, status: "starting", runId });

    let detail;
    try {
      detail = await fetchRun(runId);
    } catch (e) {
      setSnap({ ...EMPTY, status: "error", runId, error: (e as Error).message });
      return;
    }

    // Synthesize the DoneFrame the live path would have produced, so RunStatus /
    // ExportBar consume an identical shape whether streamed or reopened.
    const done: DoneFrame = {
      type: "done",
      run_id: detail.run_id,
      iterations: detail.metrics.length,
      stop_reason: String(detail.summary.stop_reason ?? ""),
      summary: detail.summary,
      verification: detail.verification,
      shape: detail.shape,
      density_b64: detail.density_b64,
    };

    setSnap({
      status: "done",
      runId: detail.run_id,
      benchmarkId: detail.benchmark_id,
      shape: detail.shape,
      density: detail.density_b64,
      iterations: detail.metrics,
      stages: [], // reopened runs have no live rail yet (history replay via /trace is deferred)
      done,
      error: null,
    });
  }, []);

  return { snap, launch, loadRun, reset };
}
