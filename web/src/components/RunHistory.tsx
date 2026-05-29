import { useState } from "react";
import type { RunListItem } from "../api/types";
import { fmt } from "../lib/format";
import "./RunHistory.css";

interface RunHistoryProps {
  runs: RunListItem[];
  activeRunId: string | null;
  disabled: boolean; // true while a live run streams — reopen is blocked
  onReopen: (runId: string) => void;
}

/**
 * Run-history panel — a collapsible list of past runs (progressive disclosure:
 * collapsed by default so the viewport stays the hero). Completed runs are
 * clickable to reopen; running/error rows are inert. Holds no fetch logic; the
 * parent owns the list and re-fetches when a run finishes.
 */
export function RunHistory({ runs, activeRunId, disabled, onReopen }: RunHistoryProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="run-history">
      <button
        type="button"
        className="run-history-header run-history-toggle"
        aria-expanded={open}
        aria-controls="run-history-body"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="run-history-title">History</span>
        <span className="run-history-count mono" aria-label={`${runs.length} runs`}>
          {runs.length}
        </span>
        <ChevronIcon open={open} />
      </button>

      {open && (
        <div className="run-history-body" id="run-history-body">
          {runs.length === 0 ? (
            <p className="run-history-empty">
              No runs yet — launch one to see it here.
            </p>
          ) : (
            <ul className="run-history-list">
              {runs.map((run) => (
                <RunHistoryRow
                  key={run.run_id}
                  run={run}
                  active={run.run_id === activeRunId}
                  disabled={disabled}
                  onReopen={onReopen}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

interface RunHistoryRowProps {
  run: RunListItem;
  active: boolean;
  disabled: boolean;
  onReopen: (runId: string) => void;
}

function RunHistoryRow({ run, active, disabled, onReopen }: RunHistoryRowProps) {
  const reopenable = run.status === "done";
  const complianceText = run.compliance != null ? fmt(run.compliance) : null;
  const dims = `${run.nelx}×${run.nely}`;

  const inner = (
    <>
      <span
        className={`run-history-dot run-history-dot--${statusKind(run.status)}`}
        aria-hidden="true"
      />
      <span className="run-history-label">{run.label}</span>
      <span className="run-history-dims mono">{dims}</span>
      {complianceText && (
        <span className="run-history-compliance mono">{complianceText}</span>
      )}
      {run.status === "done" && (
        <span
          className={
            run.verified
              ? "run-history-chip run-history-chip--ok"
              : "run-history-chip run-history-chip--warn"
          }
        >
          {run.verified ? "Verified" : "Unverified"}
        </span>
      )}
    </>
  );

  const rowClass = active
    ? "run-history-row run-history-row--active"
    : "run-history-row";

  if (reopenable) {
    const aria =
      `Reopen ${run.label} run` +
      (complianceText ? `, compliance ${complianceText}` : "");
    return (
      <li>
        <button
          type="button"
          className={`${rowClass} run-history-row--button`}
          disabled={disabled}
          aria-label={aria}
          aria-current={active ? "true" : undefined}
          onClick={() => onReopen(run.run_id)}
        >
          {inner}
        </button>
      </li>
    );
  }

  // Running / error rows are non-interactive status indicators.
  return (
    <li className={`${rowClass} run-history-row--static`} aria-current={active ? "true" : undefined}>
      {inner}
    </li>
  );
}

/** Map a run status to a dot kind (running / done / error → accent / ok / danger). */
function statusKind(status: string): "running" | "done" | "error" {
  if (status === "done") return "done";
  if (status === "error") return "error";
  return "running"; // 'running' and any transient/unknown state pulse as active
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`run-history-chevron ${open ? "is-open" : ""}`}
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M6 9l6 6 6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export type { RunHistoryProps };
