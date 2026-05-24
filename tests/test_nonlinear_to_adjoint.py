"""Wave OO (v7): geometric-nonlinear TO via full-TL adjoint sensitivity.

Quantitative anchors:
- the adjoint sensitivity dC/dρ of the converged full-Total-Lagrangian
  end-compliance matches central finite differences (the verification the
  blueprint asks for);
- the sensitivity has the correct sign (more material → lower compliance);
- the geometrically-nonlinear compliance differs from the linear one (the
  nonlinearity is real, not a relabelled linear solve).
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.nonlinear_simp import tl_adjoint_compliance_sensitivity

N_STEPS = 4


def _smoke():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def _compliance(config, mesh, rho):
    return tl_adjoint_compliance_sensitivity(config, mesh, rho, n_load_steps=N_STEPS).compliance


def test_tl_adjoint_sensitivity_matches_central_fd():
    config, mesh = _smoke()
    rng = np.random.default_rng(0)
    n = mesh.elements.shape[0]
    rho = np.clip(0.5 + 0.05 * rng.standard_normal(n), 0.3, 0.9)

    out = tl_adjoint_compliance_sensitivity(config, mesh, rho, n_load_steps=N_STEPS)
    assert out.converged

    # FD-check the most sensitive design elements (where rtol is meaningful).
    design = np.where(~mesh.void_mask)[0]
    order = design[np.argsort(-np.abs(out.sensitivity[design]))]
    h = 1e-6
    for e in order[:5]:
        rp, rm = rho.copy(), rho.copy()
        rp[e] += h
        rm[e] -= h
        fd = (_compliance(config, mesh, rp) - _compliance(config, mesh, rm)) / (2.0 * h)
        assert out.sensitivity[e] == pytest.approx(fd, rel=2e-4, abs=1e-6), (
            f"elem {e}: adjoint={out.sensitivity[e]:.6e} fd={fd:.6e}"
        )


def test_tl_adjoint_sensitivity_sign_is_negative_where_loaded():
    config, mesh = _smoke()
    rho = np.full(mesh.elements.shape[0], 0.6)
    out = tl_adjoint_compliance_sensitivity(config, mesh, rho, n_load_steps=N_STEPS)
    design = np.where(~mesh.void_mask)[0]
    # More material lowers compliance → sensitivity ≤ 0; the most-strained
    # elements are strictly negative.
    assert (out.sensitivity[design] <= 1e-9).all()
    assert out.sensitivity[design].min() < 0.0


def test_geometric_nonlinearity_changes_compliance():
    config, mesh = _smoke()
    rho = np.full(mesh.elements.shape[0], 0.6)
    # 1 load step from zero is still the full nonlinear solve; compare TL
    # compliance against the linear-elastic compliance of the same design.
    from structure_optimizer.core.fem2d import solve_linear_elastic
    tl_c = tl_adjoint_compliance_sensitivity(config, mesh, rho, n_load_steps=N_STEPS).compliance
    lin_c = float(solve_linear_elastic(config, mesh, rho).compliance)
    assert abs(tl_c - lin_c) / lin_c > 1e-6, "TL compliance indistinguishable from linear"


def test_tl_adjoint_rejects_density_mismatch():
    config, mesh = _smoke()
    from structure_optimizer.core.fem2d import SolverError
    with pytest.raises(SolverError, match="density_count_mismatch"):
        tl_adjoint_compliance_sensitivity(config, mesh, np.zeros(3), n_load_steps=N_STEPS)
