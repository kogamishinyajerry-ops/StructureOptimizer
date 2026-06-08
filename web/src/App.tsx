import { useCallback, useEffect, useState } from "react";
import { fetchBenchmarks, fetchBenchmarkConfig, fetchRuns } from "./api/client";
import { useRun } from "./api/useRun";
import type {
  BenchmarkSummary,
  BenchmarkConfigEditable,
  RunListItem,
  RunOverrides,
} from "./api/types";
import { BenchmarkPicker } from "./components/BenchmarkPicker";
import { RunControls } from "./components/RunControls";
import { ConvergenceChart } from "./components/ConvergenceChart";
import { RunStatus } from "./components/RunStatus";
import { ExportBar } from "./components/ExportBar";
import { ProblemEditor } from "./components/ProblemEditor";
import { RunHistory } from "./components/RunHistory";
import { CompareView } from "./components/CompareView";
import { DensityViewport } from "./viewport/DensityViewport";
import { GuidedMode } from "./guided/GuidedMode";
import "./App.css";

export function App() {
  const [benchmarks, setBenchmarks] = useState<BenchmarkSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preset, setPreset] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editable, setEditable] = useState<BenchmarkConfigEditable | null>(null);
  const [overrides, setOverrides] = useState<RunOverrides | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [configReload, setConfigReload] = useState(0);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [comparePair, setComparePair] = useState<[string, string] | null>(null);
  const [guided, setGuided] = useState(false);
  const { snap, launch, loadRun } = useRun();

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

  // Fetch editable defaults for the selected benchmark (or on a manual retry via
  // configReload). Overrides reset to null (null = use defaults). On failure the
  // editor surfaces an error + retry; Run still works on the benchmark defaults.
  useEffect(() => {
    if (!selectedId) {
      setEditable(null);
      setOverrides(null);
      setConfigError(null);
      return;
    }
    let cancelled = false;
    setEditable(null);
    setOverrides(null);
    setConfigError(null);
    fetchBenchmarkConfig(selectedId)
      .then((cfg) => {
        if (cancelled) return;
        setEditable(cfg);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setConfigError(e instanceof Error ? e.message : "Failed to load parameters");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, configReload]);

  // Run history: refetch on mount and whenever the active run reaches a terminal
  // state (a finished run changes the list). The cancelled flag guards against a
  // late response landing after the effect re-ran. Failures are swallowed — the
  // history panel is non-critical and degrades to its last-known list.
  useEffect(() => {
    let cancelled = false;
    fetchRuns()
      .then((list) => {
        if (!cancelled) setRuns(list);
      })
      .catch(() => {
        /* history is best-effort; keep prior list */
      });
    return () => {
      cancelled = true;
    };
  }, [snap.status]);

  const selectedBench = benchmarks.find((b) => b.id === selectedId);
  const presets = selectedBench?.presets ?? [];
  const running = snap.status === "running" || snap.status === "starting";

  // Pre-flight validation of the edited problem definition: catch cap breaches
  // client-side so the Run button is blocked with a clear reason instead of the
  // backend rejecting the request with a 400 after the click.
  const editorInvalid = validateOverrides(editable, overrides);

  const canRun = !!selectedId && !running && !editorInvalid;

  const onRun = () => {
    if (selectedId && !editorInvalid) launch(selectedId, preset ?? undefined, overrides ?? undefined);
  };

  // Reopen a finished run from history (no-op while a live run is streaming).
  const onReopen = useCallback(
    (runId: string) => {
      if (!running) loadRun(runId);
    },
    [running, loadRun],
  );

  const onCompare = useCallback((idA: string, idB: string) => {
    setComparePair([idA, idB]);
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-brand">
          <span className="app-brand-mark" aria-hidden="true" />
          <div className="app-brand-text">
            <h1 className="app-brand-name">StructureOptimizer</h1>
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
          <button
            type="button"
            className="app-guided-btn"
            onClick={() => setGuided(true)}
            disabled={running}
            // Stable focus-restore target for GuidedMode on close (WCAG 2.4.3).
            data-guided-entry
            // Chinese label under a lang="en" document (WCAG 3.1.2 Language of Parts).
            lang="zh-CN"
          >
            ▶ 讲解模式
          </button>
        </div>
      </header>

      {loadError && (
        <div className="app-banner" role="alert">
          <span className="app-banner-dot" aria-hidden="true" />
          Couldn’t load benchmarks — {loadError}
        </div>
      )}

      {editorInvalid && (
        <div className="app-banner" role="alert">
          <span className="app-banner-dot" aria-hidden="true" />
          {editorInvalid}
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
          <ProblemEditor
            config={editable}
            value={overrides}
            disabled={running}
            error={configError}
            onChange={setOverrides}
            onReset={() => setOverrides(null)}
            onRetry={() => setConfigReload((n) => n + 1)}
          />
          <RunStatus snap={snap} />
          {snap.status === "done" && snap.runId && <ExportBar runId={snap.runId} />}
          <div className="app-chart-slot">
            <ConvergenceChart iterations={snap.iterations} />
          </div>
          <RunHistory
            runs={runs}
            activeRunId={snap.runId}
            disabled={running}
            onReopen={onReopen}
            onCompare={onCompare}
          />
        </aside>
      </main>

      {comparePair && (
        <CompareView pair={comparePair} onClose={() => setComparePair(null)} />
      )}

      {guided && (
        <GuidedMode snap={snap} onLaunch={(id) => launch(id)} onExit={() => setGuided(false)} />
      )}
    </div>
  );
}

/**
 * Mirror of the backend caps (server/overrides.py) so the Run button can be
 * blocked with a human reason before the request is sent. Returns a message
 * string when the edited definition is invalid, or null when it's runnable.
 * Uses the effective values (edits layered over the benchmark defaults).
 */
function validateOverrides(
  config: BenchmarkConfigEditable | null,
  overrides: RunOverrides | null,
): string | null {
  if (!config) return null; // nothing edited yet → run uses benchmark defaults
  const mesh = overrides?.mesh ?? config.mesh;
  const opt = overrides?.optimization ?? config.optimization;
  const lim = config.limits;
  if (mesh.nelx < 4 || mesh.nely < 4) {
    return "Mesh must be at least 4×4 elements.";
  }
  if (mesh.nelx > lim.nelx_max || mesh.nely > lim.nely_max) {
    return `Mesh axis exceeds the ${lim.nelx_max}-element cap — reduce resolution to run.`;
  }
  if (mesh.nelx * mesh.nely > lim.elements_max) {
    return `Mesh exceeds the ${lim.elements_max.toLocaleString()}-element cap — reduce resolution to run.`;
  }
  if (opt.max_iterations < 1 || opt.max_iterations > lim.max_iterations_max) {
    return `Max iterations must be between 1 and ${lim.max_iterations_max}.`;
  }
  return null;
}
