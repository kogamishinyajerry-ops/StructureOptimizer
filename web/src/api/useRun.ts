import { useCallback, useEffect, useRef, useState } from "react";
import { fetchRun, fetchTrace, probeRun, startRun, streamUrl, type RunProbe } from "./client";
import type { DoneFrame, MetricPoint, RunDetail, RunOverrides, StageFrame, StreamFrame } from "./types";

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

  // Close any live socket when the hook unmounts (prevents leaks + setState-on-
  // unmounted). Nulling wsRef also makes the `wsRef.current !== ws` guard in the
  // recovery poll fire on unmount, so a stray poll can't setState afterwards.
  useEffect(
    () => () => {
      detach(wsRef.current);
      wsRef.current = null;
    },
    [],
  );

  const reset = useCallback(() => {
    detach(wsRef.current);
    wsRef.current = null;
    setSnap(EMPTY);
  }, []);

  // Build a terminal "done" snapshot from the persisted REST artifacts. Shared by
  // history-reopen (loadRun) and disconnect-recovery so both produce an identical
  // shape whether the run was streamed or fetched.
  const buildDoneFromRest = useCallback(
    async (runId: string, detail: RunDetail): Promise<RunSnapshot> => {
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
      let stages: StageFrame[] = [];
      try {
        const records = await fetchTrace(runId);
        stages = records.map((r): StageFrame => ({ type: "stage", phase: "end", agent: r.name, record: r }));
      } catch {
        stages = [];
      }
      return {
        status: "done",
        runId: detail.run_id,
        benchmarkId: detail.benchmark_id,
        shape: detail.shape,
        density: detail.density_b64,
        iterations: detail.metrics,
        stages,
        done,
        error: null,
      };
    },
    [],
  );

  // Disconnect recovery. The backend daemon keeps running to completion after a
  // WS drop, and the stream endpoint is explicitly built to send a reconnect to
  // GET /api/runs/{id}. So when the socket dies mid-run, poll REST a few times
  // before declaring failure: a transient drop / laptop-sleep on a run that
  // actually succeeded recovers to "done" instead of a false hard error.
  // Safe-by-construction: only an explicit 200 flips to "done"; a 500 or an
  // exhausted budget stays an error — a real failure is never masked as success.
  const recoverViaRest = useCallback(
    async (runId: string, ws: WebSocket): Promise<void> => {
      const DELAYS = [400, 800, 1500, 2500, 4000]; // bounded ~9s, then give up
      for (const delay of DELAYS) {
        await new Promise((r) => setTimeout(r, delay));
        if (wsRef.current !== ws) return; // superseded by a new launch / loadRun
        let probe: RunProbe;
        try {
          probe = await probeRun(runId);
        } catch {
          continue; // still unreachable — try again
        }
        if (wsRef.current !== ws) return;
        if (probe.state === "done") {
          setSnap(await buildDoneFromRest(runId, probe.detail));
          return;
        }
        if (probe.state === "errored") {
          setSnap((prev) => ({ ...prev, status: "error", error: probe.message }));
          return;
        }
        if (probe.state === "missing") {
          setSnap((prev) => ({ ...prev, status: "error", error: "Run no longer available" }));
          return;
        }
        // "running": the backend is still solving — keep polling.
      }
      if (wsRef.current !== ws) return;
      setSnap((prev) =>
        prev.status === "done"
          ? prev
          : {
              ...prev,
              status: "error",
              error:
                "Connection lost — the run may still be completing; reopen it from history once it finishes.",
            },
      );
    },
    [buildDoneFromRest],
  );

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

    // Per-launch closure state: `terminal` records that a done/error frame arrived
    // (so a following close is clean, not a mid-run drop); `recovering` ensures the
    // REST recovery poll starts at most once per socket (onerror + onclose pair).
    let terminal = false;
    let recovering = false;

    // Guard every handler: a frame queued on a superseded socket must not mutate
    // the new run's state (fast re-run race).
    ws.onmessage = (ev) => {
      if (wsRef.current !== ws) return;
      const frame = JSON.parse(ev.data) as StreamFrame;
      if (frame.type === "done" || frame.type === "error") terminal = true;
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

    // A socket error/close WITHOUT a terminal frame is a mid-run disconnect, not a
    // failure: the backend run is still alive and fetchable via REST, so recover
    // before declaring error. onerror is always followed by onclose, and a clean
    // terminal close has terminal=true, making this a no-op there; `recovering`
    // dedupes the onerror+onclose pair.
    const triggerRecovery = () => {
      if (wsRef.current !== ws || terminal || recovering) return;
      recovering = true;
      void recoverViaRest(start.run_id, ws);
    };
    ws.onerror = triggerRecovery;
    ws.onclose = triggerRecovery;
  }, [recoverViaRest]);

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

    // buildDoneFromRest synthesizes the DoneFrame the live path would have
    // produced (+ rebuilds the agent rail from the persisted trace), so a reopened
    // run consumes an identical shape whether streamed or fetched.
    setSnap(await buildDoneFromRest(runId, detail));
  }, [buildDoneFromRest]);

  return { snap, launch, loadRun, reset };
}
