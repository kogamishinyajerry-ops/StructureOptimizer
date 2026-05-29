import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { BenchmarkSummary } from "../api/types";
import "./BenchmarkPicker.css";

interface Props {
  benchmarks: BenchmarkSummary[];
  selectedId: string | null;
  disabled: boolean;
  onSelect: (id: string) => void;
}

/**
 * Benchmark selector — a compact dropdown styled as a modern-SaaS combobox.
 * Recommended benchmarks are grouped first. Closes on outside click / Escape.
 */
export function BenchmarkPicker({ benchmarks, selectedId, disabled, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = benchmarks.find((b) => b.id === selectedId) ?? null;

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const recommended = benchmarks.filter((b) => b.recommended);
  const others = benchmarks.filter((b) => !b.recommended);

  const pick = (id: string) => {
    onSelect(id);
    setOpen(false);
  };

  return (
    <div className="picker" ref={rootRef}>
      <button
        type="button"
        className="picker-trigger"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="picker-trigger-label">
          {selected ? (
            <>
              <span className="picker-name">{selected.label}</span>
              <span className="picker-dims mono">
                {selected.nelx}×{selected.nely}
              </span>
            </>
          ) : (
            <span className="picker-placeholder">Select a benchmark…</span>
          )}
        </span>
        <ChevronIcon open={open} />
      </button>

      {open && (
        <div className="picker-menu" role="listbox">
          {recommended.length > 0 && (
            <Group label="Recommended">
              {recommended.map((b) => (
                <Option key={b.id} b={b} active={b.id === selectedId} onPick={pick} />
              ))}
            </Group>
          )}
          {others.length > 0 && (
            <Group label="More">
              {others.map((b) => (
                <Option key={b.id} b={b} active={b.id === selectedId} onPick={pick} />
              ))}
            </Group>
          )}
        </div>
      )}
    </div>
  );
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="picker-group">
      <div className="picker-group-label">{label}</div>
      {children}
    </div>
  );
}

function Option({
  b,
  active,
  onPick,
}: {
  b: BenchmarkSummary;
  active: boolean;
  onPick: (id: string) => void;
}) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={active}
      className={`picker-option ${active ? "is-active" : ""}`}
      onClick={() => onPick(b.id)}
    >
      <div className="picker-option-main">
        <span className="picker-option-name">{b.label}</span>
        <span className="picker-option-dims mono">
          {b.nelx}×{b.nely} · vf {b.volume_fraction}
        </span>
      </div>
      {b.description && <span className="picker-option-desc">{b.description}</span>}
    </button>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`picker-chevron ${open ? "is-open" : ""}`}
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
