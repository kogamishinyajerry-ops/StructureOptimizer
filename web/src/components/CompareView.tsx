import { useEffect, useRef, useState } from "react";
import { fetchRun } from "../api/client";
import type { RunDetail } from "../api/types";
import { fmt, pct } from "../lib/format";
import { DensityViewport } from "../viewport/DensityViewport";
import "./CompareView.css";

interface CompareViewProps {
  pair: [string, string]; // two completed run ids to compare
  onClose: () => void;
}

/**
 * Side-by-side comparison overlay for two completed runs. Fetches both run
 * details, renders their density fields next to each other, and tabulates the
 * key response metrics with a signed delta (B - A). Frontend-only: every datum
 * comes from the existing GET /api/runs/{id} payload.
 */
export function CompareView({ pair, onClose }: CompareViewProps) {
  const [runs, setRuns] = useState<[RunDetail, RunDetail] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  // Fetch both runs (re-runs if the selected pair changes).
  useEffect(() => {
    let cancelled = false;
    setRuns(null);
    setError(null);
    Promise.all([fetchRun(pair[0]), fetchRun(pair[1])])
      .then(([a, b]) => {
        if (!cancelled) setRuns([a, b]);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load runs");
      });
    return () => {
      cancelled = true;
    };
  }, [pair]);

  // Dialog conventions: focus the close button on mount, close on Escape.
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="compare-backdrop" onClick={onClose}>
      <div
        className="compare-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Compare runs"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="compare-header">
          <span className="compare-title">Compare runs</span>
          <button
            ref={closeRef}
            type="button"
            className="compare-close"
            aria-label="Close comparison"
            onClick={onClose}
          >
            <CloseIcon />
          </button>
        </header>

        {error ? (
          <div className="compare-error" role="alert">
            Couldn&rsquo;t load runs &mdash; {error}
          </div>
        ) : runs === null ? (
          <div className="compare-loading">Loading runs&hellip;</div>
        ) : (
          <CompareBody a={runs[0]} b={runs[1]} />
        )}
      </div>
    </div>
  );
}

function CompareBody({ a, b }: { a: RunDetail; b: RunDetail }) {
  const ma = summarize(a);
  const mb = summarize(b);
  const rows: MetricRow[] = [
    { key: "compliance", label: "Compliance", a: ma.compliance, b: mb.compliance, lowerBetter: true },
    { key: "vf", label: "Volume fraction", a: ma.vf, b: mb.vf, kind: "pct" },
    { key: "mass", label: "Mass", a: ma.mass, b: mb.mass, lowerBetter: true },
    { key: "disp", label: "Max displacement", a: ma.disp, b: mb.disp, lowerBetter: true },
    { key: "stress", label: "Max stress", a: ma.stress, b: mb.stress, lowerBetter: true },
    { key: "iterations", label: "Iterations", a: ma.iterations, b: mb.iterations },
  ];

  return (
    <div className="compare-body">
      <div className="compare-panes">
        <RunPane label="A" run={a} verified={ma.verified} />
        <RunPane label="B" run={b} verified={mb.verified} />
      </div>

      <table className="compare-table">
        <thead>
          <tr>
            <th scope="col" className="compare-th-metric">Metric</th>
            <th scope="col">A</th>
            <th scope="col">B</th>
            <th scope="col">&Delta; (B &minus; A)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <MetricCells key={r.key} row={r} />
          ))}
        </tbody>
      </table>
      <p className="compare-disclaimer">
        Optimization candidates &mdash; engineering review required. Not certified results.
      </p>
    </div>
  );
}

function RunPane({ label, run, verified }: { label: string; run: RunDetail; verified: boolean | null }) {
  const benchLabel = run.benchmark_id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const [nely, nelx] = run.shape;
  return (
    <div className="compare-pane">
      <div className="compare-pane-head">
        <span className="compare-pane-tag mono">{label}</span>
        <span className="compare-pane-label">{benchLabel}</span>
        {verified !== null && (
          <span
            className={
              verified ? "compare-chip compare-chip--ok" : "compare-chip compare-chip--warn"
            }
          >
            {verified ? "Verified" : "Unverified"}
          </span>
        )}
      </div>
      <div className="compare-viewport-well">
        <DensityViewport density={run.density_b64} shape={run.shape} running={false} />
      </div>
      <div className="compare-pane-dims mono">
        {nelx}&times;{nely} &middot; {run.run_id}
      </div>
    </div>
  );
}

interface MetricRow {
  key: string;
  label: string;
  a: number | null;
  b: number | null;
  lowerBetter?: boolean;
  kind?: "pct";
}

function MetricCells({ row }: { row: MetricRow }) {
  const show = (v: number | null) =>
    v == null ? "—" : row.kind === "pct" ? pct(v) : fmt(v);

  let deltaText = "—";
  let deltaClass = "compare-delta";
  if (row.a != null && row.b != null) {
    const d = row.b - row.a;
    const sign = d > 0 ? "+" : "";
    const pctChange = row.a !== 0 ? ` (${sign}${((d / Math.abs(row.a)) * 100).toFixed(1)}%)` : "";
    deltaText = row.kind === "pct" ? `${sign}${(d * 100).toFixed(1)}pp` : `${sign}${fmt(d)}${pctChange}`;
    if (row.lowerBetter && d !== 0) {
      deltaClass += d < 0 ? " compare-delta--better" : " compare-delta--worse";
    }
  }

  return (
    <tr>
      <th scope="row" className="compare-td-metric">{row.label}</th>
      <td className="mono">{show(row.a)}</td>
      <td className="mono">{show(row.b)}</td>
      <td className={`mono ${deltaClass}`}>{deltaText}</td>
    </tr>
  );
}

interface RunMetrics {
  compliance: number | null;
  vf: number | null;
  mass: number | null;
  disp: number | null;
  stress: number | null;
  iterations: number | null;
  verified: boolean | null;
}

/** Pull comparison metrics out of a run's summary/verification payloads. */
function summarize(run: RunDetail): RunMetrics {
  const opt = obj(run.summary, "optimized");
  const lastMetric = run.metrics.length > 0 ? run.metrics[run.metrics.length - 1] : null;
  return {
    compliance: num(opt, "compliance") ?? lastMetric?.compliance ?? null,
    vf: num(run.verification, "actual_volume_fraction") ?? lastMetric?.volume_fraction ?? null,
    mass: num(opt, "mass") ?? lastMetric?.mass ?? null,
    disp: num(opt, "max_displacement") ?? lastMetric?.max_displacement ?? null,
    stress: num(opt, "max_stress"),
    iterations: num(run.summary, "iterations"),
    verified: run.verification?.status === undefined ? null : run.verification.status === "passed",
  };
}

function obj(source: Record<string, unknown> | undefined, key: string): Record<string, unknown> | undefined {
  const v = source?.[key];
  return v && typeof v === "object" ? (v as Record<string, unknown>) : undefined;
}

function num(source: Record<string, unknown> | undefined, key: string): number | null {
  const v = source?.[key];
  return typeof v === "number" && !Number.isNaN(v) ? v : null;
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M6 6l12 12M18 6L6 18"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export type { CompareViewProps };
