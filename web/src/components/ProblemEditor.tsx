import { useState } from "react";
import type {
  BenchmarkConfigEditable,
  EditableLoad,
  RunOverrides,
} from "../api/types";
import "./ProblemEditor.css";

interface ProblemEditorProps {
  config: BenchmarkConfigEditable | null; // fetched defaults for the selected benchmark (null while loading)
  value: RunOverrides | null; // current edited values (null mirrors config defaults)
  disabled: boolean; // true while a run is active
  error?: string | null; // config-fetch failure message (null while loading/ok)
  onChange: (next: RunOverrides) => void;
  onReset: () => void;
  onRetry?: () => void; // re-fetch config after a load failure
}

/**
 * Problem-definition editor — a controlled, collapsible panel (progressive
 * disclosure: collapsed by default so the viewport stays the hero). Holds no
 * fetch or run logic; the parent owns config/value and passes edits straight
 * to launch. Every onChange emits a COMPLETE RunOverrides (config defaults with
 * the user's edits applied) so the parent never has to merge partials.
 */
export function ProblemEditor(props: ProblemEditorProps) {
  const { config, value, disabled, error, onChange, onReset, onRetry } = props;
  const [open, setOpen] = useState(false);

  if (config === null) {
    // Fetch failed — show an inline error + retry instead of a permanent skeleton.
    if (error) {
      return (
        <div className="problem-editor problem-editor--error">
          <div className="problem-editor-header">
            <span className="problem-editor-title">Problem definition</span>
          </div>
          <div className="problem-editor-error" role="alert">
            <span className="problem-editor-error-text">
              Couldn’t load parameters — {error}
            </span>
            {onRetry && (
              <button type="button" className="problem-editor-retry" onClick={onRetry}>
                Retry
              </button>
            )}
          </div>
        </div>
      );
    }
    return (
      <div className="problem-editor problem-editor--loading">
        <div className="problem-editor-header">
          <span className="problem-editor-title">Problem definition</span>
          <span className="problem-editor-skeleton-pill" aria-hidden="true" />
        </div>
        <span className="problem-editor-loading-text">Loading parameters…</span>
      </div>
    );
  }

  // Effective values = user edits ?? config defaults. We always have a full set.
  const opt = value?.optimization ?? config.optimization;
  const mesh = value?.mesh ?? config.mesh;
  const loads: EditableLoad[] = config.loads_editable
    ? value?.loads ?? config.loads
    : [];

  const elements = mesh.nelx * mesh.nely;
  const overElements = elements > config.limits.elements_max;

  // Build a COMPLETE override set from current effective values, then mutate the
  // requested slice. Never emit a partial — the parent passes this to launch.
  const emit = (next: RunOverrides) => onChange(next);

  const baseOverrides = (): RunOverrides => {
    const out: RunOverrides = {
      optimization: { ...opt },
      mesh: { ...mesh },
    };
    if (config.loads_editable) out.loads = loads.map((l) => ({ ...l }));
    return out;
  };

  const setOpt = (key: keyof typeof opt, raw: number) => {
    const next = baseOverrides();
    next.optimization = { ...opt, [key]: raw };
    emit(next);
  };

  const setMesh = (key: "nelx" | "nely", raw: number) => {
    const next = baseOverrides();
    next.mesh = { ...mesh, [key]: raw };
    emit(next);
  };

  const setLoad = (index: number, key: keyof EditableLoad, raw: string | number) => {
    const next = baseOverrides();
    const editedLoads = loads.map((l, i) =>
      i === index ? { ...l, [key]: raw } : { ...l },
    );
    next.loads = editedLoads;
    emit(next);
  };

  return (
    <div className="problem-editor">
      <button
        type="button"
        className="problem-editor-header problem-editor-toggle"
        aria-expanded={open}
        aria-controls="problem-editor-body"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="problem-editor-title">Problem definition</span>
        {!open && (
          <span className="problem-editor-summary mono" aria-hidden="true">
            vf {opt.volume_fraction} · {mesh.nelx}×{mesh.nely} · {opt.max_iterations} it
          </span>
        )}
        <ChevronIcon open={open} />
      </button>

      {open && (
        <div className="problem-editor-body" id="problem-editor-body">
          <Section label="Optimization">
            <RangeField
              id="pe-vf"
              label="Volume fraction"
              min={0.05}
              max={0.95}
              step={0.05}
              value={opt.volume_fraction}
              disabled={disabled}
              format={(v) => v.toFixed(2)}
              onChange={(v) => setOpt("volume_fraction", v)}
            />
            <RangeField
              id="pe-penalty"
              label="Penalty"
              min={1}
              max={5}
              step={0.5}
              value={opt.penalty}
              disabled={disabled}
              format={(v) => v.toFixed(1)}
              onChange={(v) => setOpt("penalty", v)}
            />
            <RangeField
              id="pe-filter"
              label="Filter radius"
              min={0.5}
              max={4}
              step={0.5}
              value={opt.filter_radius}
              disabled={disabled}
              format={(v) => v.toFixed(1)}
              onChange={(v) => setOpt("filter_radius", v)}
            />
            <div className="problem-editor-field">
              <label className="problem-editor-field-label" htmlFor="pe-maxit">
                Max iterations
              </label>
              <input
                id="pe-maxit"
                className="problem-editor-number mono"
                type="number"
                min={1}
                max={config.limits.max_iterations_max}
                step={1}
                value={opt.max_iterations}
                disabled={disabled}
                onChange={(e) =>
                  setOpt("max_iterations", toInt(e.target.value, opt.max_iterations))
                }
              />
            </div>
          </Section>

          <Section label="Mesh">
            <div className="problem-editor-mesh-grid">
              <div className="problem-editor-field">
                <label className="problem-editor-field-label" htmlFor="pe-nelx">
                  Elements X
                </label>
                <input
                  id="pe-nelx"
                  className="problem-editor-number mono"
                  type="number"
                  min={4}
                  max={config.limits.nelx_max}
                  step={1}
                  value={mesh.nelx}
                  disabled={disabled}
                  onChange={(e) => setMesh("nelx", toInt(e.target.value, mesh.nelx))}
                />
              </div>
              <div className="problem-editor-field">
                <label className="problem-editor-field-label" htmlFor="pe-nely">
                  Elements Y
                </label>
                <input
                  id="pe-nely"
                  className="problem-editor-number mono"
                  type="number"
                  min={4}
                  max={config.limits.nely_max}
                  step={1}
                  value={mesh.nely}
                  disabled={disabled}
                  onChange={(e) => setMesh("nely", toInt(e.target.value, mesh.nely))}
                />
              </div>
            </div>
            <div
              className={
                overElements
                  ? "problem-editor-elements problem-editor-elements--over mono"
                  : "problem-editor-elements mono"
              }
              role="status"
              aria-live="polite"
            >
              {elements.toLocaleString()} elements
              {overElements && (
                <span className="problem-editor-elements-hint">
                  {" "}
                  — over {config.limits.elements_max.toLocaleString()} cap
                </span>
              )}
            </div>
          </Section>

          <Section label="Loads">
            {config.loads_editable ? (
              <div className="problem-editor-loads">
                {loads.map((load, i) => (
                  <div className="problem-editor-load-row" key={i}>
                    <select
                      className="problem-editor-select"
                      aria-label={`Load ${i + 1} location`}
                      value={load.selector}
                      disabled={disabled}
                      onChange={(e) => setLoad(i, "selector", e.target.value)}
                    >
                      {config.selectors.map((sel) => (
                        <option key={sel} value={sel}>
                          {sel}
                        </option>
                      ))}
                    </select>
                    <input
                      className="problem-editor-number mono"
                      type="number"
                      step={0.1}
                      aria-label={`Load ${i + 1} fx`}
                      value={load.fx}
                      disabled={disabled}
                      onChange={(e) =>
                        setLoad(i, "fx", toNum(e.target.value, load.fx))
                      }
                    />
                    <input
                      className="problem-editor-number mono"
                      type="number"
                      step={0.1}
                      aria-label={`Load ${i + 1} fy`}
                      value={load.fy}
                      disabled={disabled}
                      onChange={(e) =>
                        setLoad(i, "fy", toNum(e.target.value, load.fy))
                      }
                    />
                  </div>
                ))}
              </div>
            ) : (
              <span className="problem-editor-muted">
                Multiple load cases — not editable in this view
              </span>
            )}
          </Section>

          <button
            type="button"
            className="problem-editor-reset"
            disabled={disabled}
            onClick={onReset}
          >
            Reset to defaults
          </button>
        </div>
      )}
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="problem-editor-section">
      <div className="problem-editor-section-label">{label}</div>
      {children}
    </div>
  );
}

interface RangeFieldProps {
  id: string;
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  disabled: boolean;
  format: (v: number) => string;
  onChange: (v: number) => void;
}

function RangeField(props: RangeFieldProps) {
  const { id, label, min, max, step, value, disabled, format, onChange } = props;
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="problem-editor-field">
      <div className="problem-editor-field-head">
        <label className="problem-editor-field-label" htmlFor={id}>
          {label}
        </label>
        <span className="problem-editor-readout mono">{format(value)}</span>
      </div>
      <input
        id={id}
        className="problem-editor-range"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        style={{ "--pe-fill": `${pct}%` } as React.CSSProperties}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`problem-editor-chevron ${open ? "is-open" : ""}`}
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

/** Parse a number input, falling back to the prior value on empty / NaN. */
function toNum(raw: string, fallback: number): number {
  const n = Number(raw);
  return raw.trim() === "" || Number.isNaN(n) ? fallback : n;
}

function toInt(raw: string, fallback: number): number {
  const n = Math.round(Number(raw));
  return raw.trim() === "" || Number.isNaN(n) ? fallback : n;
}

export type { ProblemEditorProps };
