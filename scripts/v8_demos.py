"""Wave BBB (v8): closing-the-loop demo / render artifacts.

Self-contained HTML + STL demos for the v8 drivers, in the same inline-SVG,
no-external-dependency spirit as the v6/v7 demos. Each function runs a **real**
v8 computation and writes a real artifact; ``main()`` regenerates them all into
``out_dir`` (default ``build/v8_demos/``).

Demos:
- ``nonlinear_oc_demo`` — geometric-nonlinear (Total-Lagrangian) TO full OC loop
  (Wave UU): end-compliance descent history, HTML bar.
- ``seeded_nsga_demo`` — gradient-seeded NSGA-III density-field front (Wave WW):
  seeded vs random final hypervolume at the same budget, HTML.
- ``system_reliability_demo`` — general-marginal (Weibull/Gumbel) FORM β per mode
  via the Gauss-Hermite Nataf transform (Wave XX) + a series-system Ditlevsen
  bound (Wave ZZ), HTML table.
- ``fibre_steer_demo`` — fibre-steering thermal TO (Wave YY): thermal-compliance
  descent as the per-element fibre angle is steered, HTML.
- ``holed_stl_demo`` — marching-squares nested-loop holed STL (Wave AAA):
  watertight rectangular-hole prism + exact (outer − hole) cross-section area.

These are illustrative; the quantitative correctness lives in the test suite.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.multi_objective_to import (
    gradient_seeded_multi_objective_to,
    multi_objective_to,
)
from structure_optimizer.core.nonlinear_simp import nonlinear_to_oc
from structure_optimizer.core.reliability import (
    Marginal,
    build_nataf_general,
    form_hlrf,
    system_reliability_series,
)
from structure_optimizer.core.stl_export import write_stl_smooth_holes
from structure_optimizer.core.thermal_simp import (
    fibre_steering_thermal_to,
    load_thermal_benchmark,
)


def _html(title: str, body: str) -> str:
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;color:#222}"
        "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}"
        ".bar{background:#3a6;height:12px;display:inline-block}</style></head>"
        f"<body><h2>{title}</h2>{body}</body></html>"
    )


def nonlinear_oc_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """Geometric-nonlinear (Total-Lagrangian) TO full OC loop — compliance descent."""
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    res = nonlinear_to_oc(config, mesh, n_load_steps=4, max_iter=12)
    h = res.compliance_history
    hmax = max(h) or 1.0
    body = "<p>TL end-compliance per OC iteration:</p><table><tr><th>iter</th><th>C</th></tr>"
    for i, c in enumerate(h):
        body += f"<tr><td>{i}</td><td>{c:.4g} <span class='bar' style='width:{200 * c / hmax:.0f}px'></span></td></tr>"
    body += (
        f"</table><p>C {h[0]:.4g} → {h[-1]:.4g} "
        f"(converged={res.converged}); large-deformation topology, not the linear one.</p>"
    )
    Path(out_path).write_text(_html("Geometric-nonlinear TO OC loop (Total-Lagrangian)", body))
    return {"out_path": str(out_path), "c0": h[0], "c_final": h[-1], "converged": res.converged}


def seeded_nsga_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """Gradient-seeded NSGA-III vs random init — final hypervolume at same budget."""
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    kw = dict(n_generations=8, population_size=12, rng_seed=0)
    rand = multi_objective_to(config, mesh, **kw)
    seeded = gradient_seeded_multi_objective_to(
        config, mesh, seed_volume_fractions=(0.25, 0.45, 0.65), **kw)
    hv_r, hv_s = rand.hv_history[-1], seeded.hv_history[-1]
    gain = 100.0 * (hv_s - hv_r) / (hv_r + 1e-30)
    body = (
        "<table><tr><th>init</th><th>front size</th><th>final hypervolume</th></tr>"
        f"<tr><td>random</td><td>{rand.n_front}</td><td>{hv_r:.4g}</td></tr>"
        f"<tr><td>gradient-seeded</td><td>{seeded.n_front}</td><td>{hv_s:.4g}</td></tr></table>"
        f"<p>Seeding the population with gradient-SIMP optima lifts the hypervolume "
        f"by <b>{gain:+.0f}%</b> at the same generation budget.</p>"
    )
    Path(out_path).write_text(_html("Gradient-seeded NSGA-III density-field front", body))
    return {"out_path": str(out_path), "hv_random": hv_r, "hv_seeded": hv_s, "gain_pct": gain}


def system_reliability_demo(out_path: str | Path) -> dict:
    """General-marginal (Weibull/Gumbel) FORM β per mode + series Ditlevsen bound."""
    # Two failure modes, each a linear limit state over non-Gaussian variables.
    # Mode 1: g = R - S with R~lognormal (resistance), S~gumbel (max load).
    # Mode 2: g = R2 - S with R2~weibull (resistance), S~gumbel (shared load).
    betas = []
    for r_marginal in (Marginal("lognormal", float(np.log(120.0)), 0.15),
                       Marginal("weibull", 5.0, 130.0)):
        load = Marginal("gumbel", 70.0, 12.0)
        nataf = build_nataf_general([r_marginal, load])
        g = nataf.wrap_limit_state(lambda x: float(x[0] - x[1]))
        res = form_hlrf(g, n_vars=2)
        betas.append(res.beta)
    # Series system (fails if either mode fails); modes share the load → positive ρ.
    rho = np.array([[1.0, 0.5], [0.5, 1.0]])
    sysr = system_reliability_series(betas, rho)
    body = (
        "<table><tr><th>mode</th><th>β (FORM, general Nataf)</th></tr>"
        + "".join(f"<tr><td>{i + 1}</td><td>{b:.4f}</td></tr>" for i, b in enumerate(betas))
        + "</table>"
        f"<p>Series-system failure probability (Ditlevsen 2nd-order bounds): "
        f"<b>[{sysr['p_failure_lower']:.3e}, {sysr['p_failure_upper']:.3e}]</b>; "
        f"simple unimodal bounds [{sysr['simple_lower']:.3e}, {sysr['simple_upper']:.3e}].</p>"
        "<p>General marginals via the Gauss-Hermite Nataf transform; the bounds "
        "use the bivariate-normal CDF of the correlated modes.</p>"
    )
    Path(out_path).write_text(_html("System reliability: general-marginal FORM + Ditlevsen", body))
    return {"out_path": str(out_path), "betas": betas,
            "p_lower": sysr["p_failure_lower"], "p_upper": sysr["p_failure_upper"]}


def fibre_steer_demo(out_path: str | Path) -> dict:
    """Fibre-steering thermal TO — thermal-compliance descent as θ is steered."""
    config, _k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    rho = np.full(mesh.elements.shape[0], 1.0)
    res = fibre_steering_thermal_to(config, mesh, rho, kxx=5.0, kyy=1.0, n_steps=20, step=0.3,
                                    heat_sources=sources, thermal_bcs=bcs)
    h = res.compliance_history
    hmax = max(h) or 1.0
    body = "<p>Thermal compliance as fibre angles are steered:</p><table><tr><th>step</th><th>C</th></tr>"
    for i, c in enumerate(h):
        if i % 4 == 0 or i == len(h) - 1:
            body += f"<tr><td>{i}</td><td>{c:.4g} <span class='bar' style='width:{200 * c / hmax:.0f}px'></span></td></tr>"
    drop = 100.0 * (h[0] - h[-1]) / (h[0] + 1e-30)
    body += (
        f"</table><p>C {h[0]:.4g} → {h[-1]:.4g} (<b>-{drop:.0f}%</b>) by aligning the "
        f"anisotropic conductor (kxx={res.kxx:g}, kyy={res.kyy:g}) with the heat flux.</p>"
    )
    Path(out_path).write_text(_html("Fibre-steering thermal TO (orientation field)", body))
    return {"out_path": str(out_path), "c0": h[0], "c_final": h[-1], "drop_pct": drop}


def holed_stl_demo(out_dir: str | Path) -> dict:
    """Marching-squares nested-loop holed STL: rectangular hole → watertight prism."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    config = load_benchmark("cantilever", preset="smoke")
    config = replace(config, mesh=replace(config.mesh, nelx=40, nely=40, width=40.0, height=40.0))
    mesh = create_structured_mesh(config)
    rho = np.zeros(mesh.nelx * mesh.nely)
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            x, y = ex + 0.5, ey + 0.5
            solid = 6 < x < 34 and 6 < y < 34
            hole = 15 < x < 25 and 15 < y < 25
            rho[mesh.element_index(ex, ey)] = 1.0 if (solid and not hole) else 0.0
    info = write_stl_smooth_holes(mesh, rho, out_dir / "holed_block.stl")
    return {"holed_stl": info}


def main(out_dir: str | Path = "build/v8_demos") -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    d = nonlinear_oc_demo(out_dir / "nonlinear_oc.html")
    print("nonlinear_oc_demo: C", f"{d['c0']:.4g} → {d['c_final']:.4g}", "converged", d["converged"])
    s = seeded_nsga_demo(out_dir / "seeded_nsga.html")
    print("seeded_nsga_demo: HV random", f"{s['hv_random']:.4g}", "seeded", f"{s['hv_seeded']:.4g}", f"({s['gain_pct']:+.0f}%)")
    r = system_reliability_demo(out_dir / "system_reliability.html")
    print("system_reliability_demo: betas", [f"{b:.3f}" for b in r["betas"]], "Pf∈", f"[{r['p_lower']:.2e},{r['p_upper']:.2e}]")
    f = fibre_steer_demo(out_dir / "fibre_steer.html")
    print("fibre_steer_demo: C", f"{f['c0']:.4g} → {f['c_final']:.4g}", f"(-{f['drop_pct']:.0f}%)")
    g = holed_stl_demo(out_dir)
    print("holed_stl_demo: watertight", g["holed_stl"]["is_watertight"], "area", g["holed_stl"]["cross_section_area"])
    print(f"v8 demos written to {out_dir}/")


if __name__ == "__main__":
    main()
