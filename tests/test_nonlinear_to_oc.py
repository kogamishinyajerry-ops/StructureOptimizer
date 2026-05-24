"""Wave UU (v8, D050): geometric-nonlinear TO full OC loop.

Quantitative anchors:
- the full-TL adjoint OC loop reduces the (large-deformation) end-compliance and
  holds the volume constraint;
- the loop is (near-)monotone and converges;
- a TL-aware optimum has **lower TL compliance** than the linear-SIMP optimum
  evaluated under the same large-deformation solve — i.e. large deformation
  genuinely matters — and the two density fields differ.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.nonlinear_simp import (
    nonlinear_to_oc,
    tl_adjoint_compliance_sensitivity,
)
from structure_optimizer.core.simp import run_simp

N_STEPS = 4


def _smoke():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def test_nonlinear_oc_loop_and_beats_linear_under_large_deformation():
    config, mesh = _smoke()
    res = nonlinear_to_oc(config, mesh, n_load_steps=N_STEPS, max_iter=15, change_tol=5e-3)
    h = res.compliance_history

    # descent + near-monotone (TL OC can take small uphill steps mid-bisection)
    assert h[-1] < h[0]
    assert h[-1] < 0.5 * h[0]  # substantial reduction
    assert all(h[i + 1] <= h[i] * 1.05 for i in range(len(h) - 1)), f"not near-monotone: {h}"

    # volume constraint held at the target
    assert res.volume_history[-1] == pytest.approx(config.optimization.volume_fraction, rel=1e-3)

    # large deformation matters: the TL-aware optimum has lower TL compliance than
    # the linear-SIMP optimum evaluated under the same TL solve.
    lin = run_simp(config, mesh)
    c_tl_linear = tl_adjoint_compliance_sensitivity(config, mesh, lin.densities, n_load_steps=N_STEPS).compliance
    assert h[-1] <= c_tl_linear * (1.0 + 1e-9), f"TL-aware {h[-1]:.3g} not ≤ TL-of-linear {c_tl_linear:.3g}"
    # the two designs are genuinely different (not a relabelled linear solve)
    l2 = float(np.linalg.norm(res.densities - lin.densities) / np.sqrt(res.densities.size))
    assert l2 > 5e-3, f"nonlinear topology indistinguishable from linear (L2/√n={l2:.4g})"


def test_nonlinear_oc_single_step_is_well_formed():
    config, mesh = _smoke()
    res = nonlinear_to_oc(config, mesh, n_load_steps=2, max_iter=1, change_tol=0.0)
    # one OC step → initial + final compliance recorded, volume at target, design in [min,1]
    assert len(res.compliance_history) == 2
    assert res.volume_history[-1] == pytest.approx(config.optimization.volume_fraction, rel=1e-3)
    assert res.densities.min() >= config.optimization.min_density - 1e-12
    assert res.densities.max() <= 1.0 + 1e-12
    assert res.mesh_shape == (mesh.nelx, mesh.nely)
