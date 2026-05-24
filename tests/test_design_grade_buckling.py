"""Wave AAAA (v12, D082): design-grade buckling sensitivity + buckling-load max.

Quantitative anchors (FD + entry-condition + knob, not qualitative trend):
- the **design-grade** ``∂λ/∂ρ`` (with the ∂u/∂ρ adjoint term) matches central FD
  to ≤ 1e-3 — the term :func:`buckling_sensitivity` truncates;
- **D074/D082 entry condition**: a fixed-volume λ_crit ascent driven by the
  design-grade gradient *raises* λ_crit above baseline, whereas the analysis-grade
  gradient *lowers* it — closing v11's honest buckling deferral;
- **void-mode relaxation knob**: a steeper ``g_penalty`` drives a low-density
  element's geometric-stiffness contribution toward zero faster.

D074's reopening criterion: "design-grade buckling sensitivity (∂u/∂ρ +
void-mode relaxation)".
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.buckling import (
    assemble_geometric_stiffness,
    buckling_load_factor,
    buckling_sensitivity,
    design_grade_buckling_sensitivity,
    maximize_buckling_load,
)
from structure_optimizer.core.fem2d import solve_linear_elastic
from structure_optimizer.core.filtering import density_filter
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.mma import MMAState, mma_step
from structure_optimizer.core.simp import run_simp


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def _lam(config, mesh, rho):
    u = solve_linear_elastic(config, mesh, rho).displacements
    lambdas, phis = buckling_load_factor(config, mesh, rho, u, n_modes=1)
    return float(lambdas[0]), phis[:, 0], u


def test_design_grade_sensitivity_matches_central_fd():
    config, mesh = _setup()
    rho = run_simp(config, mesh).densities
    lam, phi, u = _lam(config, mesh, rho)
    dl = design_grade_buckling_sensitivity(config, mesh, rho, u, lam, phi)

    h = 1e-5
    for e in np.argsort(-np.abs(dl))[:5]:
        rp, rm = rho.copy(), rho.copy()
        rp[e] += h
        rm[e] -= h
        fd = (_lam(config, mesh, rp)[0] - _lam(config, mesh, rm)[0]) / (2.0 * h)
        rel = abs(dl[e] - fd) / (abs(fd) + 1e-30)
        assert rel <= 1e-3, f"elem {e}: design-grade {dl[e]:.4e} vs FD {fd:.4e} (rel {rel:.2e})"


def _ascent(config, mesh, sensitivity_fn, n_steps=30):
    """Fixed-volume λ_crit ascent with the given sensitivity function."""
    opt = config.optimization
    design = mesh.design_mask
    n = max(1, int(np.count_nonzero(design)))
    rho = run_simp(config, mesh).densities.copy()
    x = rho[design].copy()
    xmin, xmax = np.full(n, opt.min_density), np.ones(n)
    dfdx = np.full((1, n), 1.0 / n)
    state = MMAState()
    vf = opt.volume_fraction
    lam0 = _lam(config, mesh, rho)[0]
    last = lam0
    for _ in range(n_steps):
        rho[design] = x
        lam, phi, u = _lam(config, mesh, rho)
        last = lam
        dl = sensitivity_fn(config, mesh, rho, u, lam, phi)
        s = density_filter(mesh, rho, dl, opt.filter_radius, opt.min_density)
        x, _ = mma_step(x, -s[design], np.array([float(np.mean(x) - vf)]), dfdx, xmin, xmax, state)
    return lam0, last


def test_entry_condition_design_grade_raises_analysis_grade_lowers():
    config, mesh = _setup()
    # design-grade gradient: ascent must RAISE λ_crit above baseline (D074 gate)
    lam0_d, lam_final_d = _ascent(config, mesh, design_grade_buckling_sensitivity)
    assert lam_final_d > lam0_d, f"design-grade ascent did not raise λ_crit ({lam0_d:.2f}→{lam_final_d:.2f})"

    # analysis-grade (truncated) gradient: ascent fails to raise it (why v11 deferred)
    lam0_a, lam_final_a = _ascent(config, mesh, buckling_sensitivity)
    assert lam_final_a < lam0_a, f"analysis-grade unexpectedly raised λ_crit ({lam0_a:.2f}→{lam_final_a:.2f})"
    # design-grade is decisively better than analysis-grade
    assert lam_final_d > lam_final_a


def test_maximize_buckling_load_driver():
    config, mesh = _setup()
    design = mesh.design_mask
    vf = config.optimization.volume_fraction
    r = maximize_buckling_load(config, mesh, vf=vf, n_steps=30)
    assert r.lambda_history[-1] > r.lambda_history[0], "driver did not raise λ_crit"
    assert float(r.densities[design].mean()) <= vf + 0.02, "volume infeasible"
    # determinism
    a = maximize_buckling_load(config, mesh, vf=vf, n_steps=5)
    b = maximize_buckling_load(config, mesh, vf=vf, n_steps=5)
    assert np.allclose(a.densities, b.densities)


def test_void_mode_relaxation_knob_suppresses_low_density_kg():
    config, mesh = _setup()
    rho = run_simp(config, mesh).densities
    u = solve_linear_elastic(config, mesh, rho).displacements
    # a steeper g_penalty drives low-density K_g contributions toward zero faster:
    # the global K_g Frobenius norm shrinks as g_penalty rises (void modes suppressed)
    kg_p = assemble_geometric_stiffness(config, mesh, rho, u)  # default = opt.penalty
    kg_steep = assemble_geometric_stiffness(config, mesh, rho, u, g_penalty=2.0 * config.optimization.penalty)
    # default reproduces the original behaviour exactly
    kg_explicit = assemble_geometric_stiffness(config, mesh, rho, u, g_penalty=config.optimization.penalty)
    assert np.allclose(kg_p, kg_explicit)
    # steeper interpolation strictly reduces the (sub-unity-density) K_g magnitude
    assert np.linalg.norm(kg_steep) < np.linalg.norm(kg_p)


def test_property_design_grade_buckling_matches_fd():
    """Property: design-grade dλ/dρ matches central FD on the top elements for
    several random feasible densities."""
    config, mesh = _setup()
    n = mesh.elements.shape[0]
    rng = np.random.default_rng(0)
    h = 1e-5
    for _ in range(3):
        rho = np.clip(0.5 + 0.2 * rng.standard_normal(n), 0.3, 1.0)
        lam, phi, u = _lam(config, mesh, rho)
        dl = design_grade_buckling_sensitivity(config, mesh, rho, u, lam, phi)
        e = int(np.argmax(np.abs(dl)))
        rp, rm = rho.copy(), rho.copy()
        rp[e] += h
        rm[e] -= h
        fd = (_lam(config, mesh, rp)[0] - _lam(config, mesh, rm)[0]) / (2.0 * h)
        assert abs(dl[e] - fd) / (abs(fd) + 1e-30) <= 1e-3
