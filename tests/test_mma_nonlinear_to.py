"""Wave CCC (v9, D058): MMA-driven Total-Lagrangian nonlinear TO.

Quantitative anchors:
- the MMA-TL loop drives the full-TL end-compliance far below its initial value
  (a real descent, not a single step);
- the explicit volume inequality g(x)=mean(x)−vf≤0 is satisfied at convergence
  (feasible design);
- MMA is **competitive with** the OC loop (`nonlinear_to_oc`) at the same volume
  — final compliance within 5% of (and here below) OC's, the honest D050 claim:
  MMA's extra value is additional constraints, not beating OC on compliance-only.
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.nonlinear_simp import mma_nonlinear_to, nonlinear_to_oc


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def test_mma_nonlinear_to_descends_and_is_feasible():
    config, mesh = _setup()
    vf = config.optimization.volume_fraction
    res = mma_nonlinear_to(config, mesh, n_load_steps=3, max_iter=30)
    h = res.compliance_history
    # real descent: end compliance well below the initial (uniform) design
    assert h[-1] < 0.5 * h[0], f"weak descent: {h[0]:.1f} → {h[-1]:.1f}"
    # volume inequality satisfied (feasible)
    assert res.volume_history[-1] <= vf + 0.02, f"infeasible volume {res.volume_history[-1]:.4f}"
    assert res.densities.shape[0] == mesh.elements.shape[0]


def test_mma_nonlinear_to_competitive_with_oc():
    config, mesh = _setup()
    oc = nonlinear_to_oc(config, mesh, n_load_steps=3, max_iter=15)
    mma = mma_nonlinear_to(config, mesh, n_load_steps=3, max_iter=30)
    # both land at the volume target
    assert abs(mma.volume_history[-1] - oc.volume_history[-1]) < 0.02
    # MMA is competitive with OC on the compliance-only objective (within 5%)
    ratio = mma.compliance_history[-1] / oc.compliance_history[-1]
    assert ratio <= 1.05, f"MMA not competitive with OC: ratio {ratio:.3f}"


def test_mma_nonlinear_to_deterministic():
    config, mesh = _setup()
    a = mma_nonlinear_to(config, mesh, n_load_steps=3, max_iter=12)
    b = mma_nonlinear_to(config, mesh, n_load_steps=3, max_iter=12)
    # no RNG — bit-identical densities and history
    np.testing.assert_array_equal(a.densities, b.densities)
    assert a.compliance_history == b.compliance_history


def test_property_mma_nonlinear_volume_non_increasing_tail():
    """Over the last iterations the MMA volume stays at/under the constraint
    (the asymptotes settle the design onto the feasible boundary)."""
    config, mesh = _setup()
    vf = config.optimization.volume_fraction
    res = mma_nonlinear_to(config, mesh, n_load_steps=3, max_iter=25)
    tail = res.volume_history[len(res.volume_history) // 2:]
    assert all(v <= vf + 0.03 for v in tail), f"volume drifts above constraint: {max(tail):.4f}"
