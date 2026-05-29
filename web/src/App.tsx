import { useEffect, useState } from "react";
import { fetchBenchmarks } from "./api/client";
import { useRun } from "./api/useRun";
import type { BenchmarkSummary } from "./api/types";
import { BenchmarkPicker } from "./components/BenchmarkPicker";
import { RunControls } from "./components/RunControls";
import { ConvergenceChart } from "./components/ConvergenceChart";
import { RunStatus } from "./components/RunStatus";
import { ExportBar } from "./components/ExportBar";
import { DensityViewport } from "./viewport/DensityViewport";
import "./App.css";

export function App() {
  const [benchmarks, setBenchmarks] = useState<BenchmarkSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preset, setPreset] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const { snap, launch } = useRun();

  useEffect(() => {
    let cancelled = false;
    fetchBenchmarks()
      .then((list) => {
        if (cancelled) return;
        setBenchmarks(list);
        setSelectedId(list[0]?.id ?? null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setLoadError(e instanceof Error ? e.message : "Failed to load benchmarks");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Presets are benchmark-specific; clear the choice whenever the target changes.
  useEffect(() => {
    setPreset(null);
  }, [selectedId]);

  const selectedBench = benchmarks.find((b) => b.id === selectedId);
  const presets = selectedBench?.presets ?? [];
  const running = snap.status === "running" || snap.status === "starting";
  const canRun = !!selectedId && snap.status !== "starting" && snap.status !== "running";

  const onRun = () => {
    if (selectedId) launch(selectedId, preset ?? undefined);
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-brand">
          <span className="app-brand-mark" aria-hidden="true" />
          <div className="app-brand-text">
            <span className="app-brand-name">StructureOptimizer</span>
            <span className="app-brand-sub">Topology Workbench</span>
          </div>
        </div>

        <div className="app-header-controls">
          <BenchmarkPicker
            benchmarks={benchmarks}
            selectedId={selectedId}
            disabled={running}
            onSelect={setSelectedId}
          />
          <RunControls
            status={snap.status}
            presets={presets}
            preset={preset}
            canRun={canRun}
            onPresetChange={setPreset}
            onRun={onRun}
          />
        </div>
      </header>

      {loadError && (
        <div className="app-banner" role="alert">
          <span className="app-banner-dot" aria-hidden="true" />
          Couldn’t load benchmarks — {loadError}
        </div>
      )}

      <main className="app-main">
        <section className="app-stage">
          <div className="app-viewport-well">
            <DensityViewport density={snap.density} shape={snap.shape} running={running} />
          </div>
          <p className="app-disclaimer">
            Optimization candidate — engineering review required. Not a certified result.
          </p>
        </section>

        <aside className="app-sidebar">
          <RunStatus snap={snap} />
          {snap.status === "done" && snap.runId && <ExportBar runId={snap.runId} />}
          <div className="app-chart-slot">
            <ConvergenceChart iterations={snap.iterations} />
          </div>
        </aside>
      </main>
    </div>
  );
}
