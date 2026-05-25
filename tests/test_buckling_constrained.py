"""Wave AAAAA (v13, D090): buckling-constrained MMA (λ_crit ≥ λ_safety).

Quantitative anchors (the buckling-free baseline is the SAME driver with an inactive
constraint — a consistent reference, not a different optimiser):
- **the constraint binds and conflicts**: with λ_safety set 1.5× above the
  buckling-free compliance optimum's λ_crit, the constrained design reaches
  λ_crit ≥ λ_safety **at a measurable compliance cost** (compliance strictly higher
  than the buckling-free optimum) — the production buckling-vs-stiffness trade-off;
- **volume feasible**;
- **slack λ_safety degenerates** to plain compliance minimisation (constraint
  inactive ⟹ same compliance/λ as the buckling-free run);
- determinism; guard.

D082's reopening criterion: "buckling-*constrained* MMA (λ_crit ≥ λ_safety as a
third inequality with compliance + volume)".
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.buckling import buckling_constrained_mma
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def _free_baseline(config, mesh, vf):
    """Buckling-free compliance optimum = the same driver with an inactive
    constraint (λ_safety tiny ⟹ g₁ = 1 − λ/λ_safety ≪ 0 always)."""
    r = buckling_constrained_mma(config, mesh, lambda_safety=1e-6, vf=vf, max_iter=40)
    return r.compliance_history[-1], r.lambda_history[-1]


def test_constraint_binds_and_costs_compliance():
    config, mesh = _setup()
    vf = config.optimization.volume_fraction
    c_free, lam_free = _free_baseline(config, mesh, vf)
    lam_safety = 1.5 * lam_free
    r = buckling_constrained_mma(config, mesh, lambda_safety=lam_safety, vf=vf, max_iter=40)
    lam_con, c_con = r.lambda_history[-1], r.compliance_history[-1]
    # the constraint is met (near-binding) — λ_crit lifted from λ_free toward λ_safety
    assert lam_con >= 0.95 * lam_safety, f"λ_crit {lam_con:.3f} did not reach λ_safety {lam_safety:.3f}"
    assert lam_con > 1.3 * lam_free, "constraint did not raise λ_crit meaningfully above the free optimum"
    # and it costs compliance (the buckling-vs-stiffness trade-off)
    assert c_con > c_free, f"constrained compliance {c_con:.4e} not above free {c_free:.4e}"


def test_volume_feasible():
    config, mesh = _setup()
    vf = config.optimization.volume_fraction
    _, lam_free = _free_baseline(config, mesh, vf)
    r = buckling_constrained_mma(config, mesh, lambda_safety=1.5 * lam_free, vf=vf, max_iter=40)
    assert float(r.densities[mesh.design_mask].mean()) <= vf + 0.02


def test_slack_constraint_degenerates_to_compliance_min():
    config, mesh = _setup()
    vf = config.optimization.volume_fraction
    c_free, lam_free = _free_baseline(config, mesh, vf)
    # λ_safety well below the free optimum's λ_crit ⟹ constraint inactive
    r = buckling_constrained_mma(config, mesh, lambda_safety=0.5 * lam_free, vf=vf, max_iter=40)
    assert abs(r.compliance_history[-1] - c_free) <= 0.02 * c_free
    assert abs(r.lambda_history[-1] - lam_free) <= 0.05 * lam_free


def test_determinism():
    config, mesh = _setup()
    vf = config.optimization.volume_fraction
    a = buckling_constrained_mma(config, mesh, lambda_safety=18.0, vf=vf, max_iter=6)
    b = buckling_constrained_mma(config, mesh, lambda_safety=18.0, vf=vf, max_iter=6)
    assert np.allclose(a.densities, b.densities)
    assert np.allclose(a.lambda_history, b.lambda_history)


def test_guard_nonpositive_lambda_safety():
    config, mesh = _setup()
    with pytest.raises(SolverError, match="nonpositive_lambda_safety"):
        buckling_constrained_mma(config, mesh, lambda_safety=0.0, max_iter=1)
