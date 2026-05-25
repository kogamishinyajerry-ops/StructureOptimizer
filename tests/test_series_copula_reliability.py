"""Wave AAAAAA (v14, D098) — d-Gumbel copula wired into system_reliability_series.

Quantitative analytical anchors (bit-exact independence reproduction / comonotone
limit), never qualitative trends. Traces D093's reopening criterion: "wire the d-dim
Gumbel copula into system_reliability_series for upper-tail-dependent systems".

INTEGRATION DISCIPLINE (v14): the new `system_reliability_series_copula` must reproduce
the existing independent-series result EXACTLY at the independence copula (Gumbel θ=1),
proving the production wiring does not regress D078's Gaussian R=I path.
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    _standard_normal_cdf,
    clayton_d_copula,
    gumbel_d_copula,
    system_reliability_series_copula,
    system_reliability_series_exact,
)

_BETAS = np.array([2.0, 2.5, 3.0, 1.8])
_M = _BETAS.size


def _independent_series_pf(betas):
    return 1.0 - float(np.prod([_standard_normal_cdf(b) for b in betas]))


def test_gumbel_theta1_is_bit_exact_independence():
    """Backward-compat: Gumbel θ=1 reproduces 1 − Π Φ(β_k) to machine precision."""
    pf = system_reliability_series_copula(_BETAS, gumbel_d_copula(_M, 1.0))
    assert pf == pytest.approx(_independent_series_pf(_BETAS), abs=1e-14)


def test_matches_gaussian_exact_at_independence():
    """Gumbel θ=1 also matches D078's Genz exact series with R=I (the prior path)."""
    pf_copula = system_reliability_series_copula(_BETAS, gumbel_d_copula(_M, 1.0))
    pf_exact = system_reliability_series_exact(_BETAS, np.eye(_M), n_samples=200_000, seed=0)
    assert pf_copula == pytest.approx(pf_exact, abs=2e-4)  # Genz is MC, so loose


def test_positive_dependence_lowers_pf_monotonically():
    """Upper-tail (Gumbel θ>1) dependence lowers series P_f monotonically vs θ."""
    thetas = [1.0, 1.5, 3.0, 10.0]
    pfs = [system_reliability_series_copula(_BETAS, gumbel_d_copula(_M, t)) for t in thetas]
    assert all(pfs[i] > pfs[i + 1] for i in range(len(pfs) - 1))
    assert pfs[1] < pfs[0]  # any positive dependence is below independence


def test_comonotone_limit_approaches_max_component():
    """As θ→∞ the Gumbel series P_f → max_k Φ(−β_k) (fails when weakest mode does)."""
    max_pi = float(np.max([1.0 - _standard_normal_cdf(b) for b in _BETAS]))
    pf_big = system_reliability_series_copula(_BETAS, gumbel_d_copula(_M, 50.0))
    assert pf_big == pytest.approx(max_pi, abs=1e-3)
    # and it stays at or above the comonotone floor for any finite θ
    pf_mid = system_reliability_series_copula(_BETAS, gumbel_d_copula(_M, 3.0))
    assert pf_mid >= max_pi - 1e-9


def test_clayton_small_theta_recovers_independence():
    """Family-agnostic: a Clayton copula at θ→0⁺ also recovers the independent P_f."""
    pf = system_reliability_series_copula(_BETAS, clayton_d_copula(_M, 1e-4))
    assert pf == pytest.approx(_independent_series_pf(_BETAS), abs=1e-5)


def test_series_copula_guards():
    """Copula-dimension mismatch and empty-modes guards raise SolverError."""
    with pytest.raises(SolverError, match="system_reliability_copula_dim_mismatch"):
        system_reliability_series_copula(_BETAS, gumbel_d_copula(3, 2.0))  # dim 3 ≠ 4 modes
    with pytest.raises(SolverError, match="system_reliability_no_modes"):
        system_reliability_series_copula(np.array([]), gumbel_d_copula(2, 2.0))
