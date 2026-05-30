"""Wave RRR (v10): constraint-rich / manufacturable demo artifacts.

Self-contained HTML + STL demos for the v10 drivers, in the same inline,
no-external-dependency spirit as the v6–v9 demos. Each function runs a **real**
v10 computation and writes a real artifact; ``main()`` regenerates them all into
``out_dir`` (default ``build/v10_demos/``).

Demos:
- ``multi_constraint_demo`` — multi-constraint MMA, stress p-norm + volume (KKK).
- ``target_band_demo`` — target-band placement / minimax peak suppression (LLL).
- ``generalized_nsga_demo`` — generalised nsga3_density_to bit-identity (MMM).
- ``igd_plus_demo`` — IGD⁺ vs an analytical quarter-circle Pareto front (MMM).
- ``clayton_demo`` / ``correlated_system_demo`` — Archimedean-copula Rosenblatt
  (NNN) and correlated-system RBTO (PPP).
- ``simultaneous_mma_demo`` — simultaneous (ρ,θ) coupled MMA vs alternating (OOO).
- ``smooth_watertight_demo`` — smooth + watertight annulus STL (QQQ).

These are illustrative; the quantitative correctness lives in the test suite.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.freq_response import target_band_placement
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.modal import solve_modal
from structure_optimizer.core.multi_objective_to import (
    igd_plus,
    multi_objective_to,
    nsga3_density_to,
)
from structure_optimizer.core.nonlinear_simp import multi_constraint_mma
from structure_optimizer.core.rbto import correlated_system_rbto_simp
from structure_optimizer.core.reliability import Marginal, build_copula_rosenblatt, clayton_copula
from structure_optimizer.core.simp import run_simp
from structure_optimizer.core.stl_export import write_stl_smooth_watertight_holes
from structure_optimizer.core.thermal_simp import (
    coupled_density_orientation_to,
    load_thermal_benchmark,
    simultaneous_density_orientation_mma,
)


def _html(title: str, body: str) -> str:
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;color:#222}"
        "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}"
        ".bar{background:#3a6;height:12px;display:inline-block}</style></head>"
        f"<body><h2>{title}</h2>{body}</body></html>"
    )


def multi_constraint_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """Multi-constraint MMA: stress p-norm + volume both satisfied (KKK)."""
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    vf = config.optimization.volume_fraction
    from structure_optimizer.core.fem2d import solve_linear_elastic
    from structure_optimizer.core.stress import element_von_mises_stresses, p_norm_stress

    base = run_simp(config, mesh)
    spn_base = p_norm_stress(
        element_von_mises_stresses(config, mesh, solve_linear_elastic(config, mesh, base.densities).displacements), 8.0
    )
    sigma_limit = 0.7 * spn_base
    r = multi_constraint_mma(config, mesh, sigma_limit=sigma_limit, p=8.0, vf=vf, max_iter=60)
    body = (
        f"<p>σ-limit = 0.7·baseline = <b>{sigma_limit:.4g}</b></p>"
        f"<p>σ_PN: baseline {spn_base:.4g} → constrained <b>{r.stress_history[-1]:.4g}</b> (≤ limit)</p>"
        f"<p>volume {r.volume_history[-1]:.3f} ≤ vf {vf:.3f}; compliance {r.compliance_history[-1]:.4g}</p>"
    )
    Path(out_path).write_text(_html("Multi-constraint MMA (stress p-norm + volume)", body))
    return {"out_path": str(out_path), "sigma_final": r.stress_history[-1], "sigma_limit": sigma_limit}


def target_band_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """Target-band placement: worst-case in-band response is suppressed (LLL)."""
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    rho0 = np.where(mesh.void_mask, config.optimization.min_density, config.optimization.volume_fraction)
    w1 = float(np.sqrt(solve_modal(config, mesh, rho0, n_modes=1).omega_squared[0]))
    band = np.linspace(0.85 * w1, 1.15 * w1, 7)
    r = target_band_placement(config, mesh, band, beta=1e-4, n_steps=20, p=12.0)
    body = (
        f"<p>Band around ω₁={w1:.4g}: worst-case |response|² "
        f"<b>{r.peak_initial:.4g} → {r.peak_final:.4g}</b> "
        f"(−{100 * (1 - r.peak_final / r.peak_initial):.1f}%).</p>"
    )
    Path(out_path).write_text(_html("Target-band placement (minimax around target)", body))
    return {"out_path": str(out_path), "peak_initial": r.peak_initial, "peak_final": r.peak_final}


def generalized_nsga_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """Generalised nsga3_density_to reproduces multi_objective_to bit-for-bit (MMM)."""
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    pub = multi_objective_to(config, mesh, n_generations=6, population_size=12, rng_seed=0)
    gen = nsga3_density_to(
        config, mesh, load_cases=[list(config.loads)], n_generations=6, population_size=12, rng_seed=0
    )
    identical = bool(np.array_equal(pub.front_objectives, gen.front_objectives))
    body = (
        f"<p>multi_objective_to vs nsga3_density_to(1 load case): "
        f"front bit-identical = <b>{identical}</b>; n_front {pub.n_front}.</p>"
    )
    Path(out_path).write_text(_html("Generalised NSGA-III density driver", body))
    return {"out_path": str(out_path), "bit_identical": identical}


def igd_plus_demo(out_path: str | Path) -> dict:
    """IGD⁺ against an analytical quarter-circle Pareto front (MMM)."""
    t = np.linspace(0.0, np.pi / 2.0, 50)
    z = np.column_stack([np.cos(t), np.sin(t)])
    rows = "".join(f"<tr><td>{d:.2f}</td><td>{igd_plus(z * (1 + d), z):.4f}</td></tr>" for d in (0.0, 0.05, 0.1, 0.2))
    body = f"<p>IGD⁺ of a front pushed radially out by δ (analytical front → IGD⁺=δ):</p><table><tr><th>δ</th><th>IGD⁺</th></tr>{rows}</table>"
    Path(out_path).write_text(_html("IGD⁺ indicator vs analytical Pareto front", body))
    return {"out_path": str(out_path)}


def clayton_demo(out_path: str | Path) -> dict:
    """Archimedean-copula (Clayton) Rosenblatt transform + Kendall τ (NNN)."""
    cop = clayton_copula(4.0)
    marginals = [Marginal("normal", 10.0, 2.0), Marginal("lognormal", 0.5, 0.3)]
    rb = build_copula_rosenblatt(marginals, cop)
    x = np.array([11.5, 1.9])
    z = rb.x_to_u(x)
    x_back = rb.u_to_x(z)
    body = (
        f"<p>Clayton θ=4: Kendall τ = <b>{cop.kendall_tau():.4f}</b> (=θ/(θ+2)).</p>"
        f"<p>x={x} → z={np.array2string(z, precision=4)} → x={np.array2string(x_back, precision=4)} (round-trip).</p>"
    )
    Path(out_path).write_text(_html("Archimedean-copula (Clayton) Rosenblatt", body))
    return {"out_path": str(out_path), "kendall_tau": cop.kendall_tau()}


def correlated_system_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """Correlated system-mode RBTO: positive correlation → lighter design (PPP)."""
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    d_allows, covs = [1.3, 1.5], [0.12, 0.12]
    indep = correlated_system_rbto_simp(config, mesh, d_allows, beta_target=2.5, rho_modes=0.0, load_covs=covs)
    corr = correlated_system_rbto_simp(config, mesh, d_allows, beta_target=2.5, rho_modes=0.8, load_covs=covs)
    body = (
        f"<p>β_target 2.5: independent vf <b>{indep.volume_fraction:.3f}</b> "
        f"(β_sys {indep.beta_system:.3f}) vs correlated ρ=0.8 vf <b>{corr.volume_fraction:.3f}</b> "
        f"(β_sys {corr.beta_system:.3f}).</p>"
    )
    Path(out_path).write_text(_html("Correlated system-mode RBTO", body))
    return {"out_path": str(out_path), "vf_independent": indep.volume_fraction, "vf_correlated": corr.volume_fraction}


def simultaneous_mma_demo(out_path: str | Path) -> dict:
    """Simultaneous (ρ,θ) coupled MMA vs alternating minimisation (OOO)."""
    config, _k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    sim = simultaneous_density_orientation_mma(
        config, mesh, 5.0, 1.0, max_iter=40, heat_sources=sources, thermal_bcs=bcs
    )
    alt = coupled_density_orientation_to(
        config, mesh, 5.0, 1.0, n_outer=8, n_orient_steps=8, heat_sources=sources, thermal_bcs=bcs
    )
    cs, ca = sim.compliance_history[-1], alt.compliance_history[-1]
    body = (
        f"<p>Thermal compliance: simultaneous MMA <b>{cs:.4g}</b> vs alternating <b>{ca:.4g}</b> "
        f"(simultaneous/alternating = {cs / ca:.3f}).</p>"
    )
    Path(out_path).write_text(_html("Simultaneous (ρ,θ) coupled MMA", body))
    return {"out_path": str(out_path), "simultaneous": cs, "alternating": ca}


def smooth_watertight_demo(out_dir: str | Path) -> dict:
    """Smooth + watertight annulus STL (QQQ)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 64
    xs = np.linspace(0.0, 1.0, n)
    ys = np.linspace(0.0, 1.0, n)
    gx, gy = np.meshgrid(xs, ys, indexing="xy")
    r = np.sqrt((gx - 0.5) ** 2 + (gy - 0.5) ** 2)
    field = ((r >= 0.25) & (r <= 0.45)).astype(float)
    info = write_stl_smooth_watertight_holes(field, xs, ys, out_dir / "annulus_smooth_watertight.stl", n_samples=128)
    return {"smooth_watertight_stl": info}


def main(out_dir: str | Path = "build/v10_demos") -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(multi_constraint_demo(out_dir / "multi_constraint.html"))
    print(target_band_demo(out_dir / "target_band.html"))
    print(generalized_nsga_demo(out_dir / "generalized_nsga.html"))
    print(igd_plus_demo(out_dir / "igd_plus.html"))
    print(clayton_demo(out_dir / "clayton.html"))
    print(correlated_system_demo(out_dir / "correlated_system.html"))
    print(simultaneous_mma_demo(out_dir / "simultaneous_mma.html"))
    print(smooth_watertight_demo(out_dir))
    print(f"v10 demos written to {out_dir}/")


if __name__ == "__main__":
    main()
