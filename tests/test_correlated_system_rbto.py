"""Wave PPP (v10, D071): correlated system-mode driven RBTO.

Quantitative anchors (analytical, not qualitative trend):
- **degenerates to independent**: at ``rho_modes = 0`` the correlated system β
  (and the whole RBTO result) equals the independent ``system_rbto_simp`` (HHH)
  exactly — the bivariate-CDF Ditlevsen bounds collapse to ``1 − ∏(1 − P_i)``;
- **direction is correct**: positive inter-mode correlation **reduces** the
  series-system failure probability (modes fail together), so β_system rises
  monotonically with ``rho_modes`` at a fixed design;
- the system index is computed through the **bivariate normal CDF** Φ₂ (via
  ``system_reliability_series``), and a tighter reliability lets the bisection
  reach a **lighter feasible volume** at higher correlation.

D063's reopening criterion: correlated system modes via
``system_reliability_series(ρ)`` rather than the independent series assumption.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.rbto import (
    _correlated_system_beta,
    _system_beta,
    correlated_system_rbto_simp,
    system_rbto_simp,
)

D_ALLOWS = [1.3, 1.5]
COVS = [0.12, 0.12]


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def test_rho_zero_degenerates_to_independent_beta():
    # the β helper itself: ρ=0 ⇔ independent _system_beta, exactly
    d_nom = 1.0
    b_corr, pf_corr, betas_c = _correlated_system_beta(d_nom, D_ALLOWS, COVS, 0.0)
    b_ind, pf_ind, betas_i = _system_beta(d_nom, D_ALLOWS, COVS)
    assert abs(b_corr - b_ind) < 1e-9, f"corr(ρ=0) β {b_corr} ≠ independent {b_ind}"
    assert abs(pf_corr - pf_ind) < 1e-12
    assert np.allclose(betas_c, betas_i)


def test_positive_correlation_increases_system_beta():
    # at a fixed nominal displacement, β_system rises monotonically with ρ
    d_nom = 1.0
    betas = [_correlated_system_beta(d_nom, D_ALLOWS, COVS, rho)[0] for rho in (0.0, 0.3, 0.6, 0.9)]
    for a, b in itertools.pairwise(betas):
        assert b > a, f"β_system not increasing with ρ: {betas}"


def test_correlated_rbto_degenerates_to_system_rbto_at_rho_zero():
    config, mesh = _setup()
    corr = correlated_system_rbto_simp(config, mesh, D_ALLOWS, beta_target=2.0, rho_modes=0.0, load_covs=COVS)
    indep = system_rbto_simp(config, mesh, D_ALLOWS, beta_target=2.0, load_covs=COVS)
    assert corr.feasible == indep.feasible
    assert abs(corr.volume_fraction - indep.volume_fraction) < 1e-9
    assert abs(corr.beta_system - indep.beta_system) < 1e-9
    assert np.allclose(corr.densities, indep.densities)


def test_correlation_yields_lighter_or_equal_feasible_volume():
    config, mesh = _setup()
    # higher correlation → higher β at a given vf → the bisection can stop at a
    # lighter (or equal) feasible volume for the same β_target
    indep = correlated_system_rbto_simp(config, mesh, D_ALLOWS, beta_target=2.5, rho_modes=0.0, load_covs=COVS)
    corr = correlated_system_rbto_simp(config, mesh, D_ALLOWS, beta_target=2.5, rho_modes=0.8, load_covs=COVS)
    if indep.feasible and corr.feasible:
        assert corr.volume_fraction <= indep.volume_fraction + 1e-9, (
            f"correlated vf {corr.volume_fraction} heavier than independent {indep.volume_fraction}"
        )
    # the system index satisfies the target (feasible designs)
    if corr.feasible:
        assert corr.beta_system >= 2.5 - 1e-6


def test_correlated_rbto_input_guards():
    config, mesh = _setup()
    with pytest.raises(SolverError):
        correlated_system_rbto_simp(config, mesh, D_ALLOWS, beta_target=2.0, rho_modes=1.0)  # ρ must be <1
    with pytest.raises(SolverError):
        correlated_system_rbto_simp(config, mesh, D_ALLOWS, beta_target=2.0, rho_modes=-0.1)  # ρ ≥ 0
    with pytest.raises(SolverError):
        correlated_system_rbto_simp(config, mesh, [], beta_target=2.0)  # no modes
