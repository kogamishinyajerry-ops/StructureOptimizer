import { useCallback, useEffect, useRef, useState } from "react";
import { startRun, streamUrl } from "./client";
import type { DoneFrame, IterationFrame, RunOverrides, StreamFrame } from "./types";

export type RunStatus = "idle" | "starting" | "running" | "done" | "error";

export interface RunSnapshot {
  status: RunStatus;
  runId: string | null;
  benchmarkId: string | null;
  shape: [number, number] | null; // [nely, nelx]
  /** Latest density frame (base64 uint8), updated per iteration. */
  density: string | null;
  iterations: IterationFrame[];
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

  return { snap, launch, reset };
}
