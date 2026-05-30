"""Wave TT (v7): production-driver demo / render artifacts.

Self-contained HTML + STL demos for the v7 drivers, in the same inline-SVG,
no-external-dependency spirit as the v6 demos (D041). Each function runs a
**real** v7 computation and writes a real artifact; ``main()`` regenerates them
all into ``out_dir`` (default ``build/v7_demos/``).

Demos:
- ``rbto_demo`` — reliability-based TO: volume fraction vs reliability index β
  for a sweep of β targets (FORM→SIMP), HTML table + bar.
- ``dynamic_to_demo`` — damped frequency-response TO: dynamic-compliance descent
  history + a before/after frequency sweep (resonance avoidance), HTML.
- ``render_density_pareto`` — NSGA-III density-field (compliance, volume) Pareto
  front + hypervolume history, HTML scatter.
- ``earclip_demo`` — ear-clipping STL of a concave + holed section, reporting
  watertightness and exact cross-section area.

These are illustrative; the quantitative correctness lives in the test suite.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.freq_response import (
    minimize_dynamic_compliance,
    solve_damped_frequency_response,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.multi_objective_to import multi_objective_to
from structure_optimizer.core.rbto import rbto_simp
from structure_optimizer.core.stl_export import write_stl_polygon


def _html(title: str, body: str) -> str:
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;color:#222}"
        "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}"
        ".bar{background:#3a6;height:12px;display:inline-block}</style></head>"
        f"<body><h2>{title}</h2>{body}</body></html>"
    )


def _d_nominal_at(config, mesh, vf: float) -> float:
    """Max displacement of the min-compliance design at volume fraction vf."""
    from dataclasses import replace

    from structure_optimizer.core.simp import run_simp

    cfg = replace(config, optimization=replace(config.optimization, volume_fraction=vf))
    return float(run_simp(cfg, mesh).final_analysis.max_displacement)


def rbto_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """Reliability-based TO: tightened volume fraction vs β target (FORM→SIMP)."""
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    # Calibrate the allowable from a mid-vf design so β targets are in-bracket.
    d_allow = _d_nominal_at(config, mesh, 0.45) * 1.6
    rows = []
    for beta_target in (1.0, 2.0, 3.0):
        res = rbto_simp(
            config, mesh, d_allow=d_allow, beta_target=beta_target, load_cov=0.15, vf_low=0.2, vf_high=0.85, max_iter=8
        )
        rows.append((beta_target, res.volume_fraction, res.beta))
    vmax = max(r[1] for r in rows) or 1.0
    body = "<table><tr><th>β target</th><th>volume fraction</th><th>β achieved</th></tr>"
    for bt, vf, beta in rows:
        body += (
            f"<tr><td>{bt:.1f}</td><td>{vf:.3f} "
            f"<span class='bar' style='width:{200 * vf / vmax:.0f}px'></span></td>"
            f"<td>{beta:.3f}</td></tr>"
        )
    body += "</table><p>Higher reliability target → more material.</p>"
    Path(out_path).write_text(_html("RBTO: volume vs β target", body))
    return {"out_path": str(out_path), "rows": rows}


def dynamic_to_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """Damped frequency-response (dynamic-compliance) descent + resonance avoidance.

    Also the nonlinear/damped-TO demo: writes J-descent history and the
    before/after frequency-sweep peak magnitude.
    """
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    opt = config.optimization
    omega, alpha, beta = 50.0, 0.5, 1e-4
    rho0 = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    res = minimize_dynamic_compliance(config, mesh, omega, alpha, beta, n_steps=20, move=0.1)
    sweep = np.linspace(10.0, 120.0, 28)

    def peak(r):
        return max(solve_damped_frequency_response(config, mesh, r, float(w), alpha, beta).max_magnitude for w in sweep)

    p0, p1 = peak(rho0), peak(res.densities)
    h = res.objective_history
    jmax = max(h) or 1.0
    body = "<p>Dynamic-compliance descent J = |fᵀû|²:</p><table><tr><th>step</th><th>J</th></tr>"
    for i, j in enumerate(h):
        body += f"<tr><td>{i}</td><td>{j:.4g} <span class='bar' style='width:{200 * j / jmax:.0f}px'></span></td></tr>"
    body += (
        f"</table><p>Resonance peak over 10–120 rad/s: <b>{p0:.4g} → {p1:.4g}</b> "
        f"(volume preserved at {float(np.mean(res.densities[mesh.design_mask])):.3f}).</p>"
    )
    Path(out_path).write_text(_html("Damped frequency-response TO (dynamic compliance)", body))
    return {"out_path": str(out_path), "peak_before": p0, "peak_after": p1, "j0": h[0], "j_final": h[-1]}


def render_density_pareto(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """NSGA-III density-field Pareto front render (compliance vs volume) + HV."""
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    res = multi_objective_to(config, mesh, n_generations=10, population_size=12, rng_seed=0)
    obj = res.front_objectives
    cmin, cmax = float(obj[:, 0].min()), float(obj[:, 0].max())
    pts = ""
    for ci, vi in obj:
        px = 40 + 320 * (ci - cmin) / (cmax - cmin + 1e-30)
        py = 220 - 200 * vi
        pts += f"<circle cx='{px:.1f}' cy='{py:.1f}' r='4' fill='#3a6'/>"
    svg = (
        f"<svg width='400' height='250'>{pts}"
        "<text x='180' y='245'>compliance →</text>"
        "<text x='5' y='20'>↑ volume</text></svg>"
    )
    body = (
        f"<p>{res.n_front} non-dominated density fields; "
        f"hypervolume {res.hv_history[0]:.4g} → {res.hv_history[-1]:.4g} (monotone).</p>{svg}"
    )
    Path(out_path).write_text(_html("Density-field NSGA-III Pareto front", body))
    return {"out_path": str(out_path), "n_front": res.n_front, "hv_final": res.hv_history[-1]}


def earclip_demo(out_dir: str | Path) -> dict:
    """Ear-clipping STL demo: a concave L-shape with a rectangular hole."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outer = [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (4.0, 4.0), (4.0, 10.0), (0.0, 10.0)]
    hole = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
    info = write_stl_polygon(outer, out_dir / "concave_holed.stl", holes=[hole], z_thickness=2.0)
    return {"earclip_stl": info}


def main(out_dir: str | Path = "build/v7_demos") -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print("rbto_demo:", rbto_demo(out_dir / "rbto.html")["rows"])
    d = dynamic_to_demo(out_dir / "dynamic_to.html")
    print("dynamic_to_demo: peak", d["peak_before"], "→", d["peak_after"])
    print("render_density_pareto:", render_density_pareto(out_dir / "density_pareto.html")["n_front"])
    print("earclip_demo:", earclip_demo(out_dir)["earclip_stl"]["is_watertight"])
    print(f"v7 demos written to {out_dir}/")


if __name__ == "__main__":
    main()
