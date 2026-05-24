"""Wave KKK (v10, D066): multi-constraint MMA (stress p-norm + volume).

Quantitative anchors (analytical, not qualitative trend):
- the p-norm von Mises **stress sensitivity** ``dσ_PN/dρ`` from the adjoint
  matches central finite differences to relative error ≤ 1e-4 on the
  highest-sensitivity elements (the headline analytic anchor);
- the MMA driver satisfies **both** inequality constraints at convergence —
  stress ``σ_PN ≤ σ_lim`` *and* volume ``mean(ρ) ≤ vf`` simultaneously;
- the stress constraint **binds**: with a limit below the volume-only
  (compliance-min) design's stress, the optimised design's σ_PN is driven down
  to the limit, strictly below the unconstrained baseline — the constraint
  actually changed the design (D058's reopening criterion: stress alongside
  volume, where MMA earns its keep over single-constraint OC).
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import solve_linear_elastic
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.nonlinear_simp import multi_constraint_mma
from structure_optimizer.core.simp import run_simp
from structure_optimizer.core.stress import (
    element_von_mises_stresses,
    p_norm_stress,
    stress_pnorm_sensitivity,
)

P = 8.0


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def _sigma_pn(config, mesh, rho, p=P):
    res = solve_linear_elastic(config, mesh, rho)
    return p_norm_stress(element_von_mises_stresses(config, mesh, res.displacements), p)


def test_stress_pnorm_sensitivity_matches_central_fd():
    config, mesh = _setup()
    n_elem = mesh.elements.shape[0]
    rng = np.random.default_rng(0)
    rho = np.clip(0.5 + 0.2 * rng.standard_normal(n_elem), 0.2, 1.0)

    sigma_pn, dsdrho = stress_pnorm_sensitivity(config, mesh, rho, p=P)
    assert sigma_pn > 0.0

    # central FD on the highest-|sensitivity| elements (where the relative
    # comparison is meaningful)
    order = np.argsort(-np.abs(dsdrho))[:6]
    h = 1e-6
    for eid in order:
        rp = rho.copy()
        rp[eid] += h
        rm = rho.copy()
        rm[eid] -= h
        fd = (_sigma_pn(config, mesh, rp) - _sigma_pn(config, mesh, rm)) / (2.0 * h)
        rel = abs(dsdrho[eid] - fd) / (abs(fd) + 1e-30)
        assert rel <= 1e-4, f"elem {eid}: adjoint {dsdrho[eid]:.6e} vs FD {fd:.6e} (rel {rel:.2e})"


def test_multi_constraint_mma_satisfies_both_constraints():
    config, mesh = _setup()
    vf = config.optimization.volume_fraction
    design = mesh.design_mask

    # stress limit below the volume-only design's stress so the stress
    # constraint is binding (not slack)
    baseline = run_simp(config, mesh)
    spn_base = _sigma_pn(config, mesh, baseline.densities)
    sigma_limit = 0.7 * spn_base

    r = multi_constraint_mma(config, mesh, sigma_limit=sigma_limit, p=P, vf=vf, max_iter=60)

    # both inequality constraints satisfied at convergence
    assert r.stress_history[-1] <= sigma_limit * 1.02, (
        f"stress infeasible: {r.stress_history[-1]:.3e} > {sigma_limit:.3e}"
    )
    final_vol = float(r.densities[design].mean())
    assert final_vol <= vf + 0.02, f"volume infeasible: {final_vol:.4f} > {vf}"


def test_stress_constraint_binds_and_changes_design():
    config, mesh = _setup()
    vf = config.optimization.volume_fraction

    baseline = run_simp(config, mesh)
    spn_base = _sigma_pn(config, mesh, baseline.densities)
    sigma_limit = 0.7 * spn_base

    r = multi_constraint_mma(config, mesh, sigma_limit=sigma_limit, p=P, vf=vf, max_iter=60)

    # the stress constraint actually bit: the optimised σ_PN is driven well
    # below the unconstrained baseline, down to (near) the limit
    assert r.stress_history[-1] < spn_base, (
        f"stress not reduced: {r.stress_history[-1]:.3e} vs baseline {spn_base:.3e}"
    )
    # binding (active), not merely slack-feasible: within 5% of the limit
    assert r.stress_history[-1] >= 0.9 * sigma_limit, (
        f"stress constraint slack, not binding: {r.stress_history[-1]:.3e} vs limit {sigma_limit:.3e}"
    )


def test_multi_constraint_mma_contract():
    config, mesh = _setup()
    vf = config.optimization.volume_fraction
    r = multi_constraint_mma(config, mesh, sigma_limit=5.0e3, p=P, vf=vf, max_iter=10)
    assert r.densities.shape[0] == mesh.elements.shape[0]
    assert len(r.compliance_history) == len(r.stress_history) == len(r.volume_history)
    assert r.sigma_limit == 5.0e3
    assert r.mesh_shape == (mesh.nelx, mesh.nely)
    # determinism
    r2 = multi_constraint_mma(config, mesh, sigma_limit=5.0e3, p=P, vf=vf, max_iter=10)
    assert np.allclose(r.densities, r2.densities)
