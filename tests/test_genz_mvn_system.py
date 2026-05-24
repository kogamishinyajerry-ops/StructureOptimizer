"""Wave WWW (v11, D078): exact multivariate system P_f via the Genz MVN-CDF.

Quantitative anchors (exact-degeneracy + bounds cross-check, not qualitative):
- **Genz reduces to the exact bivariate Φ₂**: the m-variate Genz estimator at
  m = 2 matches the exact Gauss-Legendre ``bivariate_normal_cdf`` to ≤ 1e-3;
- **Genz is exact for an independent correlation**: ``Φ_m(b; I) = Π Φ(b_i)`` to
  ≤ 1e-12 (the off-diagonal-free Cholesky makes every sample's product exact);
- **the exact series-system P_f lies inside the Ditlevsen bounds**: the
  full-correlation-matrix Genz value sits within the second-order bracket from
  ``system_reliability_series`` — a genuine independent cross-check;
- determinism + non-SPD / shape error handling.

D055/D071's reopening criterion: "full correlation matrix; exact multivariate
system P_f (Genz)" — the Ditlevsen result is only a bracket.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    _standard_normal_cdf,
    bivariate_normal_cdf,
    genz_mvn_cdf,
    system_reliability_series,
    system_reliability_series_exact,
)


def test_genz_reduces_to_exact_bivariate():
    for b1, b2, rho in [(1.0, 1.5, 0.5), (0.8, 0.8, -0.3), (2.0, 1.0, 0.7)]:
        r = np.array([[1.0, rho], [rho, 1.0]])
        g = genz_mvn_cdf([b1, b2], r, n_samples=40000, seed=0)
        exact = bivariate_normal_cdf(b1, b2, rho)
        assert abs(g - exact) <= 1e-3, f"b=({b1},{b2}) rho={rho}: genz {g} vs exact {exact}"


def test_genz_exact_for_independent():
    b = [1.0, 1.5, 0.5]
    g = genz_mvn_cdf(b, np.eye(3), n_samples=40000, seed=0)
    prod = float(np.prod([_standard_normal_cdf(x) for x in b]))
    assert abs(g - prod) <= 1e-12


def test_genz_one_dimensional():
    # m=1 collapses to the univariate Φ
    assert abs(genz_mvn_cdf([1.3], np.array([[1.0]])) - _standard_normal_cdf(1.3)) < 1e-12


def test_exact_series_pf_within_ditlevsen_bounds():
    rng = np.random.default_rng(1)
    alpha = rng.standard_normal((4, 3))
    alpha /= np.linalg.norm(alpha, axis=1, keepdims=True)
    r = alpha @ alpha.T
    np.fill_diagonal(r, 1.0)
    r = 0.98 * r + 0.02 * np.eye(4)  # nudge strictly SPD
    betas = np.array([2.5, 2.0, 3.0, 2.2])

    pf = system_reliability_series_exact(betas, r, n_samples=40000, seed=0)
    bd = system_reliability_series(betas, r)
    # the exact value sits inside the second-order bracket (1 % MC slack)
    assert bd["p_failure_lower"] * 0.99 <= pf <= bd["p_failure_upper"] * 1.01
    # and the bracket is genuinely non-trivial (lower < upper)
    assert bd["p_failure_lower"] < bd["p_failure_upper"]


def test_genz_determinism_and_errors():
    r = np.array([[1.0, 0.4], [0.4, 1.0]])
    assert genz_mvn_cdf([1.0, 1.0], r, seed=0) == genz_mvn_cdf([1.0, 1.0], r, seed=0)
    # non-SPD correlation
    with pytest.raises(SolverError):
        genz_mvn_cdf([1.0, 1.0], np.array([[1.0, 2.0], [2.0, 1.0]]))
    # shape mismatch
    with pytest.raises(SolverError):
        genz_mvn_cdf([1.0, 1.0, 1.0], r)
    with pytest.raises(SolverError):
        system_reliability_series_exact([], np.zeros((0, 0)))
