"""Wave JJJ (v9): second-order-driver demo / render artifacts.

Self-contained HTML + STL demos for the v9 drivers, in the same inline-SVG,
no-external-dependency spirit as the v6/v7/v8 demos. Each function runs a **real**
v9 computation and writes a real artifact; ``main()`` regenerates them all into
``out_dir`` (default ``build/v9_demos/``).

Demos:
- ``mma_tl_demo`` — MMA-driven Total-Lagrangian nonlinear TO (Wave CCC): end-
  compliance descent + competitiveness vs the OC loop.
- ``band_gap_demo`` — eigenfrequency band-gap maximisation (Wave DDD): gap widens.
- ``three_objective_demo`` — ≥3-objective multi-load NSGA-III (Wave EEE): seeded
  vs random final hypervolume.
- ``rosenblatt_demo`` — Rosenblatt transform + FORM β (Wave FFF).
- ``system_rbto_demo`` — system-reliability-based TO to a target system β (Wave HHH).
- ``coupled_orientation_demo`` — coupled density+orientation thermal TO (Wave GGG).
- ``slit_free_demo`` — slit-free watertight annulus STL (Wave III).

These are illustrative; the quantitative correctness lives in the test suite.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.freq_response import maximize_band_gap
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.multi_objective_to import multi_load_case_to
from structure_optimizer.core.nonlinear_simp import mma_nonlinear_to, nonlinear_to_oc
from structure_optimizer.core.rbto import system_rbto_simp
from structure_optimizer.core.reliability import build_rosenblatt_normal, form_hlrf
from structure_optimizer.core.simp import run_simp
from structure_optimizer.core.stl_export import write_stl_slit_free_holes
from structure_optimizer.core.thermal_simp import coupled_density_orientation_to, load_thermal_benchmark


def _html(title: str, body: str) -> str:
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;color:#222}"
        "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}"
        ".bar{background:#3a6;height:12px;display:inline-block}</style></head>"
        f"<body><h2>{title}</h2>{body}</body></html>"
    )


def mma_tl_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """MMA-driven TL nonlinear TO: compliance descent + competitiveness vs OC."""
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    mma = mma_nonlinear_to(config, mesh, n_load_steps=3, max_iter=30)
    oc = nonlinear_to_oc(config, mesh, n_load_steps=3, max_iter=15)
    h = mma.compliance_history
    hmax = max(h) or 1.0
    body = "<p>MMA TL end-compliance per iteration:</p><table><tr><th>iter</th><th>C</th></tr>"
    for i, c in enumerate(h):
        if i % 4 == 0 or i == len(h) - 1:
            body += (
                f"<tr><td>{i}</td><td>{c:.4g} <span class='bar' style='width:{200 * c / hmax:.0f}px'></span></td></tr>"
            )
    ratio = h[-1] / oc.compliance_history[-1]
    body += f"</table><p>C {h[0]:.4g} → {h[-1]:.4g}; MMA/OC = <b>{ratio:.3f}</b> at the same volume.</p>"
    Path(out_path).write_text(_html("MMA-driven Total-Lagrangian nonlinear TO", body))
    return {"out_path": str(out_path), "c_final": h[-1], "mma_over_oc": ratio}


def band_gap_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """Eigenfrequency band-gap maximisation: the gap ω²₂−ω²₁ widens."""
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    res = maximize_band_gap(config, mesh, lower_mode=0, n_steps=15, move=0.1)
    g0, gf = res.gap_history[0], res.gap_history[-1]
    body = (
        f"<p>Band gap ω²₂−ω²₁: <b>{g0:.4g} → {gf:.4g}</b> (×{gf / g0:.2f}).</p>"
        f"<p>ω² initial {np.array2string(res.omega2_initial, precision=3)} → "
        f"final {np.array2string(res.omega2_final, precision=3)}.</p>"
    )
    Path(out_path).write_text(_html("Eigenfrequency band-gap maximisation", body))
    return {"out_path": str(out_path), "gap0": g0, "gap_final": gf}


def three_objective_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """≥3-objective multi-load NSGA-III: seeded vs random final hypervolume."""
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    design = mesh.design_mask
    seeds = [
        run_simp(replace(config, optimization=replace(config.optimization, volume_fraction=vf)), mesh).densities[design]
        for vf in (0.3, 0.5, 0.7)
    ]
    rand = multi_load_case_to(config, mesh, n_generations=8, population_size=16, rng_seed=0)
    seeded = multi_load_case_to(config, mesh, n_generations=8, population_size=16, rng_seed=0, seed_genomes=seeds)
    body = (
        "<table><tr><th>init</th><th>front size</th><th>final hypervolume (3-obj)</th></tr>"
        f"<tr><td>random</td><td>{rand.n_front}</td><td>{rand.hv_history[-1]:.4g}</td></tr>"
        f"<tr><td>gradient-seeded</td><td>{seeded.n_front}</td><td>{seeded.hv_history[-1]:.4g}</td></tr></table>"
        "<p>Objectives: compliance under two conflicting load cases + volume.</p>"
    )
    Path(out_path).write_text(_html("Multi-load-case 3-objective NSGA-III", body))
    return {"out_path": str(out_path), "hv_random": rand.hv_history[-1], "hv_seeded": seeded.hv_history[-1]}


def rosenblatt_demo(out_path: str | Path) -> dict:
    """Rosenblatt transform of a correlated trivariate normal + FORM β."""
    mean = np.array([2.0, -1.0, 0.5])
    cov = np.array([[1.0, 0.3, -0.2], [0.3, 1.5, 0.1], [-0.2, 0.1, 0.8]])
    rt = build_rosenblatt_normal(mean, cov)
    a, a0 = np.array([1.0, 1.0, 1.0]), 8.0
    beta = form_hlrf(rt.wrap_limit_state(lambda x: a0 - a @ x), n_vars=3).beta
    beta_cf = (a0 - a @ mean) / np.sqrt(a @ cov @ a)
    body = (
        f"<p>Rosenblatt transform of X ~ N(μ, Σ) (conditional CDF chain).</p>"
        f"<p>FORM β through the Rosenblatt-wrapped limit state = <b>{beta:.4f}</b>; "
        f"closed form (a₀−aᵀμ)/√(aᵀΣa) = {beta_cf:.4f}.</p>"
    )
    Path(out_path).write_text(_html("Rosenblatt transform + FORM", body))
    return {"out_path": str(out_path), "beta": beta, "beta_closed_form": beta_cf}


def system_rbto_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """System-reliability-based TO: drive a 2-mode series system to a target β."""
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    d_mid = float(
        run_simp(
            replace(config, optimization=replace(config.optimization, volume_fraction=0.45)), mesh
        ).final_analysis.max_displacement
    )
    da = d_mid * 1.6
    res = system_rbto_simp(
        config, mesh, [da, da * 1.1], beta_target=2.0, load_covs=[0.15, 0.15], vf_low=0.2, vf_high=0.85
    )
    body = (
        f"<p>2-mode series system, target β = 2.0.</p>"
        f"<p>Selected volume fraction <b>{res.volume_fraction:.3f}</b>; system β = "
        f"<b>{res.beta_system:.3f}</b>; per-mode β = {[round(b, 3) for b in res.per_mode_betas]} "
        f"(system below each — two ways to fail).</p>"
    )
    Path(out_path).write_text(_html("System-reliability-based TO", body))
    return {"out_path": str(out_path), "volume_fraction": res.volume_fraction, "beta_system": res.beta_system}


def coupled_orientation_demo(out_path: str | Path) -> dict:
    """Coupled density + orientation thermal TO vs each single field."""
    config, _k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    coupled = coupled_density_orientation_to(
        config, mesh, 5.0, 1.0, n_outer=8, n_orient_steps=8, heat_sources=sources, thermal_bcs=bcs
    )
    density_only = coupled_density_orientation_to(
        config, mesh, 5.0, 1.0, n_outer=8, n_orient_steps=0, heat_sources=sources, thermal_bcs=bcs
    )
    c, d = coupled.compliance_history[-1], density_only.compliance_history[-1]
    body = (
        f"<p>Alternating density + fibre-orientation thermal TO.</p>"
        f"<p>Coupled C = <b>{c:.4g}</b> vs density-only {d:.4g} (×{d / c:.2f} better).</p>"
    )
    Path(out_path).write_text(_html("Coupled density + orientation thermal TO", body))
    return {"out_path": str(out_path), "coupled": c, "density_only": d}


def slit_free_demo(out_dir: str | Path) -> dict:
    """Slit-free watertight annulus STL (the curved hole AAA could not seal)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    config = load_benchmark("cantilever", preset="smoke")
    config = replace(config, mesh=replace(config.mesh, nelx=40, nely=40, width=40.0, height=40.0))
    mesh = create_structured_mesh(config)
    rho = np.zeros(mesh.nelx * mesh.nely)
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            r = np.hypot(ex + 0.5 - 20.0, ey + 0.5 - 20.0)
            rho[mesh.element_index(ex, ey)] = 1.0 if 7.0 < r < 15.0 else 0.0
    info = write_stl_slit_free_holes(mesh, rho, out_dir / "annulus_slit_free.stl")
    return {"slit_free_stl": info}


def main(out_dir: str | Path = "build/v9_demos") -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    m = mma_tl_demo(out_dir / "mma_tl.html")
    print("mma_tl_demo: C_final", f"{m['c_final']:.4g}", "MMA/OC", f"{m['mma_over_oc']:.3f}")
    b = band_gap_demo(out_dir / "band_gap.html")
    print("band_gap_demo: gap", f"{b['gap0']:.4g} → {b['gap_final']:.4g}")
    t = three_objective_demo(out_dir / "three_objective.html")
    print("three_objective_demo: HV random", f"{t['hv_random']:.4g}", "seeded", f"{t['hv_seeded']:.4g}")
    r = rosenblatt_demo(out_dir / "rosenblatt.html")
    print("rosenblatt_demo: beta", f"{r['beta']:.4f}", "cf", f"{r['beta_closed_form']:.4f}")
    s = system_rbto_demo(out_dir / "system_rbto.html")
    print("system_rbto_demo: vf", f"{s['volume_fraction']:.3f}", "beta_sys", f"{s['beta_system']:.3f}")
    c = coupled_orientation_demo(out_dir / "coupled_orientation.html")
    print("coupled_orientation_demo: coupled", f"{c['coupled']:.4g}", "vs density-only", f"{c['density_only']:.4g}")
    sf = slit_free_demo(out_dir)
    print(
        "slit_free_demo: annulus watertight",
        sf["slit_free_stl"]["is_watertight"],
        "area",
        sf["slit_free_stl"]["cross_section_area"],
    )
    print(f"v9 demos written to {out_dir}/")


if __name__ == "__main__":
    main()
