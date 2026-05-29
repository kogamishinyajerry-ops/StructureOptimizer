import type { RunSnapshot } from "../api/useRun";
import { fmt, pct } from "../lib/format";
import "./RunStatus.css";

interface RunStatusProps {
  snap: RunSnapshot;
}

interface Metric {
  label: string;
  value: string;
}

export function RunStatus({ snap }: RunStatusProps) {
  const latest =
    snap.iterations.length > 0
      ? snap.iterations[snap.iterations.length - 1]
      : null;

  const metrics: Metric[] = [
    { label: "Iteration", value: latest ? String(latest.iteration) : "—" },
    { label: "Compliance", value: latest ? fmt(latest.compliance) : "—" },
    {
      label: "Volume fraction",
      value: latest ? pct(latest.volume_fraction) : "—",
    },
    { label: "Change", value: latest ? fmt(latest.change) : "—" },
  ];

  return (
    <div className="run-status">
      <div className="run-status-metrics" aria-live="polite">
        {metrics.map((m) => (
          <div className="run-status-metric" key={m.label}>
            <span className="run-status-metric-label">{m.label}</span>
            <span className="run-status-metric-value mono">{m.value}</span>
          </div>
        ))}
      </div>
      <div className="run-status-state">{renderState(snap)}</div>
    </div>
  );
}

function renderState(snap: RunSnapshot) {
  switch (snap.status) {
    case "idle":
      return <span className="run-status-badge run-status-badge--idle">Idle</span>;
    case "starting":
      return (
        <span className="run-status-badge run-status-badge--starting">
          Starting…
        </span>
      );
    case "running":
      return (
        <span className="run-status-badge run-status-badge--running">
          <span className="run-status-dot" aria-hidden="true" />
          Optimizing…
        </span>
      );
    case "done": {
      const done = snap.done;
      const verification = (done?.verification ?? {}) as Record<string, unknown>;
      const rawStatus = verification.status;
      const verifyStatus =
        rawStatus === undefined || rawStatus === null
          ? "unknown"
          : String(rawStatus);
      const passed = verifyStatus === "passed";
      const stopReason = done ? String(done.stop_reason) : "";
      return (
        <div className="run-status-done">
          <span
            className={
              passed
                ? "run-status-badge run-status-badge--passed"
                : "run-status-badge run-status-badge--warn"
            }
          >
            {passed ? "Verified" : verifyStatus}
          </span>
          {stopReason ? (
            <span className="run-status-reason">stopped: {stopReason}</span>
          ) : null}
        </div>
      );
    }
    case "error":
      return (
        <div className="run-status-error">
          {snap.error ?? "An unknown error occurred."}
        </div>
      );
    default:
      return null;
  }
}

export type { RunStatusProps };
