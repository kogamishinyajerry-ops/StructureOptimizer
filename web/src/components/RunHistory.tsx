import { useState } from "react";
import type { RunListItem } from "../api/types";
import { fmt } from "../lib/format";
import "./RunHistory.css";

interface RunHistoryProps {
  runs: RunListItem[];
  activeRunId: string | null;
  disabled: boolean; // true while a live run streams — reopen/compare is blocked
  onReopen: (runId: string) => void;
  onCompare: (idA: string, idB: string) => void;
}

/**
 * Run-history panel — a collapsible list of past runs (progressive disclosure:
 * collapsed by default so the viewport stays the hero). Completed runs are
 * clickable to reopen; a compare mode lets the user pick exactly two finished
 * runs to open side by side. Holds only transient selection state; the parent
 * owns the list and the comparison overlay.
 */
export function RunHistory({ runs, activeRunId, disabled, onReopen, onCompare }: RunHistoryProps) {
  const [open, setOpen] = useState(false);
  const [compareMode, setCompareMode] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);

  const doneCount = runs.filter((r) => r.status === "done").length;

  const exitCompare = () => {
    setCompareMode(false);
    setSelected([]);
  };

  const toggleSelect = (runId: string) => {
    setSelected((prev) => {
      if (prev.includes(runId)) return prev.filter((id) => id !== runId);
      if (prev.length >= 2) return [prev[1], runId]; // keep the most recent two
      return [...prev, runId];
    });
  };

  const runCompare = () => {
    if (selected.length === 2) {
      onCompare(selected[0], selected[1]);
      exitCompare();
    }
  };

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
            <p className="run-history-empty">No runs yet — launch one to see it here.</p>
          ) : (
            <>
              {doneCount >= 2 && (
                <div className="run-history-toolbar">
                  {compareMode ? (
                    <>
                      <span className="run-history-toolbar-hint">
                        {selected.length}/2 selected
                      </span>
                      <button
                        type="button"
                        className="run-history-action run-history-action--ghost"
                        onClick={exitCompare}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        className="run-history-action run-history-action--primary"
                        disabled={selected.length !== 2}
                        onClick={runCompare}
                      >
                        Compare
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="run-history-action"
                      disabled={disabled}
                      onClick={() => setCompareMode(true)}
                    >
                      Compare runs
                    </button>
                  )}
                </div>
              )}
              <ul className="run-history-list">
                {runs.map((run) => (
                  <RunHistoryRow
                    key={run.run_id}
                    run={run}
                    active={run.run_id === activeRunId}
                    disabled={disabled}
                    compareMode={compareMode}
                    selected={selected.includes(run.run_id)}
                    onReopen={onReopen}
                    onToggleSelect={toggleSelect}
                  />
                ))}
              </ul>
            </>
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
  compareMode: boolean;
  selected: boolean;
  onReopen: (runId: string) => void;
  onToggleSelect: (runId: string) => void;
}

function RunHistoryRow({
  run,
  active,
  disabled,
  compareMode,
  selected,
  onReopen,
  onToggleSelect,
}: RunHistoryRowProps) {
  const reopenable = run.status === "done";
  const complianceText = run.compliance != null ? fmt(run.compliance) : null;
  const dims = `${run.nelx}×${run.nely}`;

  const inner = (
    <>
      {compareMode && reopenable && (
        <span
          className={selected ? "run-history-check run-history-check--on" : "run-history-check"}
          aria-hidden="true"
        >
          {selected ? "✓" : ""}
        </span>
      )}
      <span
        className={`run-history-dot run-history-dot--${statusKind(run.status)}`}
        aria-hidden="true"
      />
      <span className="run-history-label">{run.label}</span>
      <span className="run-history-dims mono">{dims}</span>
      {complianceText && <span className="run-history-compliance mono">{complianceText}</span>}
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

  const rowClass =
    (active ? "run-history-row run-history-row--active" : "run-history-row") +
    (selected ? " run-history-row--selected" : "");

  if (reopenable) {
    const aria = compareMode
      ? `${selected ? "Deselect" : "Select"} ${run.label} run for comparison`
      : `Reopen ${run.label} run` + (complianceText ? `, compliance ${complianceText}` : "");
    return (
      <li>
        <button
          type="button"
          className={`${rowClass} run-history-row--button`}
          disabled={disabled}
          aria-label={aria}
          aria-pressed={compareMode ? selected : undefined}
          aria-current={!compareMode && active ? "true" : undefined}
          onClick={() => (compareMode ? onToggleSelect(run.run_id) : onReopen(run.run_id))}
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
