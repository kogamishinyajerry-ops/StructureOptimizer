import type { RunStatus } from "../api/useRun";
import "./RunControls.css";

interface RunControlsProps {
  status: RunStatus;
  presets: string[];
  preset: string | null; // null = "Full run" (no preset)
  canRun: boolean;
  onPresetChange: (preset: string | null) => void;
  onRun: () => void;
}

const RUN_LABELS: Record<RunStatus, string> = {
  idle: "Run optimization",
  error: "Run optimization",
  starting: "Starting…",
  running: "Optimizing…",
  done: "Run again",
};

export function RunControls(props: RunControlsProps) {
  const { status, presets, preset, canRun, onPresetChange, onRun } = props;

  const busy = status === "starting" || status === "running";

  return (
    <div className="run-controls">
      <select
        className="run-controls__select"
        aria-label="Preset"
        value={preset ?? ""}
        disabled={busy}
        onChange={(event) => onPresetChange(event.target.value || null)}
      >
        <option value="">Full run</option>
        {presets.map((entry) => (
          <option key={entry} value={entry}>
            {entry}
          </option>
        ))}
      </select>

      <button
        type="button"
        className="run-controls__run"
        disabled={busy || !canRun}
        onClick={onRun}
      >
        {busy && <span className="run-controls__spinner" aria-hidden="true" />}
        {RUN_LABELS[status]}
      </button>
    </div>
  );
}
