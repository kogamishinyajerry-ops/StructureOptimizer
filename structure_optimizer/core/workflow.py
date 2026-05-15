from __future__ import annotations

from pathlib import Path

from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.config import effective_load_cases
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.reporting import generate_report
from structure_optimizer.core.run_store import (
    create_run_dir,
    input_hash,
    save_density,
    save_input,
    save_metrics,
    write_json,
)
from structure_optimizer.core.simp import run_simp
from structure_optimizer.core.verification import verify_run
from structure_optimizer.visualization import (
    write_baseline_png,
    write_convergence_png,
    write_density_gif,
    write_density_png,
    write_loadcase_png,
)


def run_benchmark(benchmark: str, preset: str | None = None) -> Path:
    config = load_benchmark(benchmark, preset=preset)
    return run_config(config)


def run_config(config, run_dir: Path | None = None) -> Path:
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    if run_dir is None:
        run_dir = create_run_dir(config)
    else:
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=False)

    save_input(run_dir, config)
    save_metrics(run_dir, result.metrics)
    save_density(run_dir, result.densities)
    write_baseline_png(run_dir / "baseline.png", mesh)
    display_loads = [load for load_case in effective_load_cases(config) for load in load_case.loads]
    write_loadcase_png(run_dir / "loadcase.png", mesh, config.boundary_conditions, display_loads)
    write_density_png(run_dir / "density.png", mesh, result.densities)
    write_convergence_png(run_dir / "convergence.png", result.metrics)
    _write_optimization_frames(run_dir, mesh, result.density_history)
    write_density_gif(run_dir / "optimization.gif", mesh, _select_animation_frames(result.density_history))

    write_json(
        run_dir / "summary.json",
        {
            "benchmark": config.name,
            "input_hash": input_hash(config),
            "status": "completed",
            "stop_reason": result.stop_reason,
            "iterations": len(result.metrics),
            "baseline": {
                "mass": result.baseline.mass,
                "compliance": result.baseline.compliance,
                "max_displacement": result.baseline.max_displacement,
                "max_stress": result.baseline.max_stress,
            },
            "optimized": {
                "mass": result.final_analysis.mass,
                "compliance": result.final_analysis.compliance,
                "max_displacement": result.final_analysis.max_displacement,
                "max_stress": result.final_analysis.max_stress,
            },
        },
    )
    verify_run(run_dir)
    generate_report(run_dir)
    return run_dir


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
