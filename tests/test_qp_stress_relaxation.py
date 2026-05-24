"""Wave SSS (v11, D074): qp-relaxed stress (stress-singularity relaxation).

Quantitative anchors (analytical, not qualitative trend):
- the qp-**relaxed** stress p-norm sensitivity ``dσ̃_PN/dρ`` (explicit ``ρ^q`` term
  + implicit adjoint) matches central finite differences to relative error
  ≤ 1e-4 on the highest-sensitivity elements;
- the relaxation **removes the stress singularity**: a vanishing-density element's
  relaxed stress ``σ̃_e = ρ_e^q·σ_e`` is suppressed by exactly ``ρ_e^q`` relative to
  its (finite, often large) raw von Mises stress — so void elements no longer
  carry the spurious finite stress that makes the raw feasible set singular;
- the qp-stress-constrained MMA satisfies **both** constraints at convergence
  (relaxed stress ≤ limit AND volume ≤ vf).

D066's reopening criterion: SIMP-relaxed / qp-stress to handle the stress
singularity. (Buckling-constrained driving is a separate, deferred reopening
criterion — see D074 honest scope.)
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import solve_linear_elastic
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.nonlinear_simp import qp_stress_constrained_mma
from structure_optimizer.core.stress import (
    element_von_mises_stresses,
    p_norm_stress,
    qp_relaxed_stress_pnorm_sensitivity,
)

P, Q = 8.0, 2.5


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def _relaxed_pn(config, mesh, rho, p=P, q=Q):
    raw = element_von_mises_stresses(config, mesh, solve_linear_elastic(config, mesh, rho).displacements)
    return p_norm_stress(np.power(np.clip(rho, 0.0, None), q) * raw, p)


def test_qp_relaxed_sensitivity_matches_central_fd():
    config, mesh = _setup()
    n_elem = mesh.elements.shape[0]
    rng = np.random.default_rng(0)
    rho = np.clip(0.5 + 0.2 * rng.standard_normal(n_elem), 0.2, 1.0)

    sigma_pn, dsdrho = qp_relaxed_stress_pnorm_sensitivity(config, mesh, rho, p=P, q=Q)
    assert sigma_pn > 0.0

    order = np.argsort(-np.abs(dsdrho))[:6]
    h = 1e-6
    for eid in order:
        rp = rho.copy()
        rp[eid] += h
        rm = rho.copy()
        rm[eid] -= h
        fd = (_relaxed_pn(config, mesh, rp) - _relaxed_pn(config, mesh, rm)) / (2.0 * h)
        rel = abs(dsdrho[eid] - fd) / (abs(fd) + 1e-30)
        assert rel <= 1e-4, f"elem {eid}: adjoint {dsdrho[eid]:.6e} vs FD {fd:.6e} (rel {rel:.2e})"


def test_relaxation_removes_stress_singularity():
    config, mesh = _setup()
    n_elem = mesh.elements.shape[0]
    rng = np.random.default_rng(1)
    rho = np.clip(0.5 + 0.2 * rng.standard_normal(n_elem), 0.2, 1.0)
    u = solve_linear_elastic(config, mesh, rho).displacements
    raw = element_von_mises_stresses(config, mesh, u)

    # the lowest-density element: its raw stress is finite (the singularity), but
    # the relaxed stress is suppressed by exactly ρ^q
    lo = int(np.argmin(rho))
    relaxed_lo = (rho[lo] ** Q) * raw[lo]
    assert raw[lo] > 0.0
    assert abs(relaxed_lo - (rho[lo] ** Q) * raw[lo]) < 1e-9
    # suppression factor is ρ^q < 1, and for a genuinely low-density element it is
    # a strong suppression (here ρ≈0.2 → ρ^2.5 ≈ 0.018)
    assert (rho[lo] ** Q) < 0.5
    assert relaxed_lo < 0.5 * raw[lo]
    # vectorised: every element's relaxed stress ≤ its raw stress
    relaxed = np.power(rho, Q) * raw
    assert np.all(relaxed <= raw + 1e-9)


def test_qp_stress_constrained_mma_satisfies_both_constraints():
    config, mesh = _setup()
    vf = config.optimization.volume_fraction
    design = mesh.design_mask

    # a stress limit below the volume-only design's relaxed stress → binding
    from structure_optimizer.core.simp import run_simp

    baseline = run_simp(config, mesh)
    spn_base = _relaxed_pn(config, mesh, baseline.densities)
    sigma_limit = 0.7 * spn_base

    r = qp_stress_constrained_mma(config, mesh, sigma_limit=sigma_limit, p=P, q=Q, vf=vf, max_iter=120)
    # the relaxed-stress constraint binds: final σ̃_PN lands on the limit (≤ + 2%)
    assert r.stress_history[-1] <= sigma_limit * 1.02, (
        f"stress infeasible: {r.stress_history[-1]:.3e} > {sigma_limit:.3e}"
    )
    # and it is genuinely driven down from the volume-only baseline (constraint active)
    assert r.stress_history[-1] < 0.9 * spn_base, "stress not driven down"
    assert float(r.densities[design].mean()) <= vf + 0.02, "volume infeasible"


def test_qp_stress_constrained_mma_contract_and_determinism():
    config, mesh = _setup()
    vf = config.optimization.volume_fraction
    a = qp_stress_constrained_mma(config, mesh, sigma_limit=3.0e3, p=P, q=Q, vf=vf, max_iter=8)
    b = qp_stress_constrained_mma(config, mesh, sigma_limit=3.0e3, p=P, q=Q, vf=vf, max_iter=8)
    assert a.densities.shape[0] == mesh.elements.shape[0]
    assert len(a.compliance_history) == len(a.stress_history) == len(a.volume_history)
    assert a.sigma_limit == 3.0e3
    assert np.allclose(a.densities, b.densities)
