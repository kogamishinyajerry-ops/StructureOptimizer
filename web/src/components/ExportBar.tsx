import { useState } from "react";
import { downloadExport, type ExportFormat } from "../api/client";
import "./ExportBar.css";

interface ExportBarProps {
  runId: string;
}

const FORMATS: { format: ExportFormat; label: string; hint: string }[] = [
  { format: "svg", label: "SVG", hint: "2D vector outline" },
  { format: "dxf", label: "DXF", hint: "CAD line entities (R12)" },
  { format: "stl", label: "STL", hint: "2.5D extruded mesh" },
];

/**
 * Geometry export — appears once a run completes. One button per format;
 * each downloads the optimized boundary as an attachment from the backend.
 * Surfaces per-format busy + error state inline.
 */
export function ExportBar({ runId }: ExportBarProps) {
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onExport = async (format: ExportFormat) => {
    setBusy(format);
    setError(null);
    try {
      await downloadExport(runId, format);
    } catch (e) {
      setError(`${format.toUpperCase()} export failed — ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="export-bar">
      <div className="export-bar-header">
        <h2 className="export-bar-label">Export geometry</h2>
      </div>
      <div className="export-bar-buttons">
        {FORMATS.map(({ format, label, hint }) => (
          <button
            key={format}
            type="button"
            className="export-btn"
            disabled={busy !== null}
            title={hint}
            aria-label={`Download ${label} — ${hint}`}
            onClick={() => onExport(format)}
          >
            {busy === format ? <span className="export-btn-spinner" aria-hidden /> : <DownloadIcon />}
            <span className="export-btn-label">{label}</span>
          </button>
        ))}
      </div>
      {error && (
        <div className="export-bar-error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}

function DownloadIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 3v12m0 0l-4-4m4 4l4-4M5 21h14"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
