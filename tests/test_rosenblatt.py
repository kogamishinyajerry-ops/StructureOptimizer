"""Wave FFF (v9, D061): Rosenblatt transform for a known joint distribution.

Quantitative anchors:
- for a multivariate normal the conditional-CDF Rosenblatt map equals the
  Cholesky whitening u = L⁻¹(x−μ) (two independent derivations agree, machine
  precision) — the headline;
- round-trip x→u→x is the identity;
- the transform decorrelates exactly: Cov(U) = L⁻¹ Σ L⁻ᵀ = I;
- for unit-variance Gaussian marginals Rosenblatt and Nataf coincide, and FORM β
  through the Rosenblatt-wrapped linear limit state equals the closed form
  (a₀−aᵀμ)/√(aᵀΣa).
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    Marginal,
    build_nataf,
    build_rosenblatt_normal,
    correlated_gaussian_reliability,
    form_hlrf,
)


def _random_spd(rng, n):
    a = rng.standard_normal((n, n))
    return a @ a.T + 0.5 * np.eye(n)


def test_property_rosenblatt_equals_cholesky_whitening():
    rng = np.random.default_rng(0)
    for _ in range(30):
        n = int(rng.integers(2, 5))
        mean = rng.uniform(-2.0, 2.0, n)
        cov = _random_spd(rng, n)
        rt = build_rosenblatt_normal(mean, cov)
        L = np.linalg.cholesky(cov)
        x = rng.uniform(-3.0, 3.0, n)
        u = rt.x_to_u(x)
        np.testing.assert_allclose(u, np.linalg.solve(L, x - mean), atol=1e-10)


def test_rosenblatt_round_trip():
    rng = np.random.default_rng(1)
    mean = np.array([2.0, -1.0, 0.5])
    cov = _random_spd(rng, 3)
    rt = build_rosenblatt_normal(mean, cov)
    x = np.array([3.1, 0.2, 1.0])
    np.testing.assert_allclose(rt.u_to_x(rt.x_to_u(x)), x, atol=1e-10)
    u = np.array([-0.4, 1.3, 0.7])
    np.testing.assert_allclose(rt.x_to_u(rt.u_to_x(u)), u, atol=1e-10)


def test_rosenblatt_decorrelates_exactly():
    rng = np.random.default_rng(2)
    cov = _random_spd(rng, 4)
    L = np.linalg.cholesky(cov)
    Linv = np.linalg.inv(L)
    cov_u = Linv @ cov @ Linv.T  # covariance of U = L⁻¹(X−μ)
    np.testing.assert_allclose(cov_u, np.eye(4), atol=1e-10)


def test_rosenblatt_matches_nataf_for_unit_variance_gaussians():
    R = np.array([[1.0, 0.5, -0.3], [0.5, 1.0, 0.2], [-0.3, 0.2, 1.0]])
    rt = build_rosenblatt_normal(np.zeros(3), R)
    nat = build_nataf([Marginal("normal", 0.0, 1.0)] * 3, R)
    x = np.array([0.7, -0.4, 1.2])
    np.testing.assert_allclose(rt.x_to_u(x), nat.x_to_u(x), atol=1e-10)


def test_rosenblatt_form_beta_matches_closed_form():
    mean = np.array([2.0, -1.0, 0.5])
    rng = np.random.default_rng(3)
    cov = _random_spd(rng, 3)
    a = np.array([1.0, 1.0, 1.0])
    a0 = 8.0
    rt = build_rosenblatt_normal(mean, cov)
    beta = form_hlrf(rt.wrap_limit_state(lambda x: a0 - a @ x), n_vars=3).beta
    beta_cf = (a0 - a @ mean) / np.sqrt(a @ cov @ a)
    assert beta == pytest.approx(beta_cf, rel=1e-6)
    # and agrees with the Nataf-based correlated_gaussian_reliability (std + corr)
    std = np.sqrt(np.diag(cov))
    corr = cov / np.outer(std, std)
    beta_nataf = correlated_gaussian_reliability(mean, std, corr, lambda x: a0 - a @ x).beta
    assert beta == pytest.approx(beta_nataf, rel=1e-6)


def test_contracts():
    with pytest.raises(SolverError, match="cov_shape_mismatch"):
        build_rosenblatt_normal(np.zeros(3), np.eye(2))
    with pytest.raises(SolverError, match="cov_not_symmetric"):
        build_rosenblatt_normal(np.zeros(2), np.array([[1.0, 0.5], [0.0, 1.0]]))
    with pytest.raises(SolverError, match="cov_not_positive_definite"):
        build_rosenblatt_normal(np.zeros(2), np.array([[1.0, 2.0], [2.0, 1.0]]))
