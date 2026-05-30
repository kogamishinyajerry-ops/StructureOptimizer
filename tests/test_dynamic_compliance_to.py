"""Wave RR (v7, D047): damped frequency-response TO (dynamic compliance).

Quantitative anchors:
- the self-adjoint dynamic-compliance sensitivity matches central differences
  of J = |fᵀû|² (the blueprint's headline anchor);
- with zero damping the dynamic compliance is real and J equals the undamped
  (fᵀu)² of the existing real solver;
- the sensitivity drives a volume-preserving descent that monotonically lowers J
  and cuts the resonance peak over a frequency sweep.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.freq_response import (
    dynamic_compliance_sensitivity,
    minimize_dynamic_compliance,
    solve_damped_frequency_response,
    solve_frequency_response,
)
from structure_optimizer.core.mesh import create_structured_mesh

OMEGA, ALPHA, BETA = 50.0, 0.5, 1e-4


def _smoke():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def test_dynamic_compliance_sensitivity_matches_central_fd():
    config, mesh = _smoke()
    rng = np.random.default_rng(1)
    n = mesh.elements.shape[0]
    rho = np.clip(0.5 + 0.1 * rng.standard_normal(n), 0.2, 0.95)

    out = dynamic_compliance_sensitivity(config, mesh, rho, OMEGA, ALPHA, BETA)
    assert out.converged

    def J(r):
        return dynamic_compliance_sensitivity(config, mesh, r, OMEGA, ALPHA, BETA).objective

    design = np.where(mesh.design_mask)[0]
    order = design[np.argsort(-np.abs(out.sensitivity[design]))]
    h = 1e-6
    for e in order[:6]:
        rp, rm = rho.copy(), rho.copy()
        rp[e] += h
        rm[e] -= h
        fd = (J(rp) - J(rm)) / (2.0 * h)
        assert out.sensitivity[e] == pytest.approx(fd, rel=1e-5), (
            f"elem {e}: adjoint={out.sensitivity[e]:.6e} fd={fd:.6e}"
        )


def test_undamped_dynamic_compliance_is_real_and_matches_real_solver():
    config, mesh = _smoke()
    rho = np.full(mesh.elements.shape[0], 0.6)
    out = dynamic_compliance_sensitivity(config, mesh, rho, OMEGA, alpha=0.0, beta=0.0)
    # zero damping → real dynamic stiffness → c real
    assert abs(out.dynamic_compliance.imag) < 1e-6 * (abs(out.dynamic_compliance.real) + 1.0)
    # J = (fᵀu)² of the undamped real solver
    real = solve_frequency_response(config, mesh, rho, OMEGA)
    from structure_optimizer.core.freq_response import _build_harmonic_load

    f = _build_harmonic_load(config, mesh)
    c_real = float(f @ real.displacements)
    assert out.objective == pytest.approx(c_real**2, rel=1e-8)


def test_descent_lowers_dynamic_compliance_monotonically():
    config, mesh = _smoke()
    res = minimize_dynamic_compliance(config, mesh, OMEGA, ALPHA, BETA, n_steps=20, move=0.1)
    h = res.objective_history
    assert len(h) == 21
    assert all(h[i + 1] <= h[i] * (1.0 + 1e-9) for i in range(len(h) - 1)), f"not monotone: {h}"
    assert h[-1] < 0.5 * h[0]  # substantial reduction


def test_descent_cuts_the_resonance_peak():
    config, mesh = _smoke()
    opt = config.optimization
    rho0 = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    res = minimize_dynamic_compliance(config, mesh, OMEGA, ALPHA, BETA, n_steps=20, move=0.1)
    sweep = np.linspace(10.0, 120.0, 28)

    def peak(r):
        return max(solve_damped_frequency_response(config, mesh, r, float(w), ALPHA, BETA).max_magnitude for w in sweep)

    assert peak(res.densities) < peak(rho0)
    # volume preserved by the descent
    assert float(np.mean(res.densities[mesh.design_mask])) == pytest.approx(opt.volume_fraction, rel=1e-6)


def test_contracts():
    config, mesh = _smoke()
    rho = np.full(mesh.elements.shape[0], 0.6)
    with pytest.raises(SolverError, match="density_count_mismatch"):
        dynamic_compliance_sensitivity(config, mesh, np.zeros(3), OMEGA)
    with pytest.raises(SolverError, match="negative_omega"):
        dynamic_compliance_sensitivity(config, mesh, rho, -1.0)
    with pytest.raises(SolverError, match="negative_coefficient"):
        dynamic_compliance_sensitivity(config, mesh, rho, OMEGA, alpha=-0.1)
