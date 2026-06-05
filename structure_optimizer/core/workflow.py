from __future__ import annotations

from pathlib import Path

from structure_optimizer.benchmarks.registry import load_benchmark

# ``run_config`` delegates to the deterministic pipeline orchestrator (see
# structure_optimizer/core/pipeline.py); the per-stage seam imports live there
# now. Only ``write_density_png`` remains here, used by the frame helpers that
# ``ExportReportAgent`` imports back from this module.
from structure_optimizer.visualization import write_density_png


def run_benchmark(benchmark: str, preset: str | None = None, algorithm: str | None = None) -> Path:
    """Load a built-in benchmark (+ optional preset, + optional algorithm override) and run the full pipeline.

    ``algorithm`` of ``"simp"`` or ``"beso"`` overrides ``config.optimization.algorithm``.
    None keeps the config-defined choice (defaults to ``"simp"``).
    """
    config = load_benchmark(benchmark, preset=preset)
    if algorithm is not None:
        from dataclasses import replace

        config = replace(config, optimization=replace(config.optimization, algorithm=algorithm))
    return run_config(config)


def run_config(
    config,
    run_dir: Path | None = None,
    parent_id: str | None = None,
    study_id: str | None = None,
    generation: int = 0,
    on_iteration=None,
    on_stage=None,
) -> Path:
    """Run mesh → algorithm (SIMP or BESO) → save artifacts → verify → report.

    Returns the run directory. Algorithm selection is driven by
    ``config.optimization.algorithm``; the default ``"simp"`` preserves all
    pre-v1.7 behavior.

    Lineage (Wave O): when ``parent_id`` / ``study_id`` / ``generation`` are
    provided, a ``lineage.json`` is written into the run dir for downstream
    tree-building. Defaults preserve v1/v2 behavior (no parent → fresh
    root-of-tree run).

    ``on_iteration`` (web runner): optional observational callback forwarded to
    the algorithm and called once per iteration with ``(iteration,
    IterationMetric, densities)``. ``None`` (default, CLI/study path) preserves
    the original behaviour exactly.

    ``on_stage`` (web runner): optional observational callback forwarded to the
    orchestrator and called per pipeline stage with a metadata-only event
    ``{"phase": "start"|"end"|"error", "agent": name, "record": dict|None}``.
    ``None`` (default, CLI/study path) emits nothing and stays byte-identical.
    """
    # Load-bearing delegation: the deterministic six-agent orchestrator IS the
    # implementation of this pipeline (there is no second code path). It runs the
    # identical seam functions with identical arguments in the identical order,
    # so every artifact is byte-identical; it additionally writes a per-run
    # ``agents_trace.json``. See structure_optimizer/core/pipeline.py.
    from structure_optimizer.core.pipeline import PipelineContext, PipelineOrchestrator

    ctx = PipelineContext(
        config=config,
        run_dir=run_dir,
        parent_id=parent_id,
        study_id=study_id,
        generation=generation,
        on_iteration=on_iteration,
        on_stage=on_stage,
    )
    return PipelineOrchestrator().run(ctx)


def _write_optimization_frames(run_dir: Path, mesh, density_history) -> None:
    frame_dir = run_dir / "optimization_frames"
    frame_dir.mkdir(exist_ok=True)
    frames = _select_animation_frames(density_history)
    for idx, densities in enumerate(frames):
        write_density_png(frame_dir / f"frame_{idx:03d}.png", mesh, densities, scale=6)


def _select_animation_frames(density_history: list) -> list:
    if len(density_history) <= 8:
        return density_history
    indexes = sorted({round(i * (len(density_history) - 1) / 7) for i in range(8)})
    return [density_history[index] for index in indexes]
