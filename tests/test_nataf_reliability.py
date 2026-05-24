"""Wave PP (v7, D045): Nataf transform — correlated / non-Gaussian FORM.

Quantitative anchors:
- Φ⁻¹ inverts Φ to ~1e-12 (the marginal transform's backbone);
- a correlated-Gaussian linear limit state reproduces the exact closed form
  β = (a₀ − aᵀμ)/√(aᵀΣa);
- the lognormal–lognormal equivalent normal correlation matches its closed
  form, and lognormal marginal round-trips exactly;
- an identity-correlation Nataf reduces to the independent standardisation.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    Marginal,
    _standard_normal_cdf,
    _standard_normal_ppf,
    build_nataf,
    correlated_gaussian_reliability,
    standardize_gaussian,
)


def test_ppf_inverts_cdf():
    for x in np.linspace(-4.0, 4.0, 33):
        p = _standard_normal_cdf(float(x))
        assert _standard_normal_ppf(p) == pytest.approx(x, abs=1e-10)


def test_ppf_known_quantiles():
    assert _standard_normal_ppf(0.5) == pytest.approx(0.0, abs=1e-12)
    assert _standard_normal_ppf(0.975) == pytest.approx(1.959963984540054, abs=1e-9)


def _beta_exact(a0, a, mean, cov):
    num = a0 - a @ mean
    return num / np.sqrt(a @ cov @ a)


def test_correlated_gaussian_linear_limit_state_matches_closed_form():
    mean = np.array([10.0, 8.0, 5.0])
    std = np.array([2.0, 1.5, 1.0])
    corr = np.array([[1.0, 0.5, -0.3], [0.5, 1.0, 0.2], [-0.3, 0.2, 1.0]])
    cov = np.diag(std) @ corr @ np.diag(std)
    a0, a = 40.0, np.array([1.0, 1.0, 1.0])

    def g(x):  # failure when a·x > a0
        return a0 - a @ np.asarray(x)

    res = correlated_gaussian_reliability(mean, std, corr, g)
    assert res.converged
    assert res.beta == pytest.approx(_beta_exact(a0, a, mean, cov), rel=1e-6)


def test_correlation_changes_beta_vs_independent():
    mean = np.array([10.0, 10.0])
    std = np.array([2.0, 2.0])
    a0, a = 25.0, np.array([1.0, 1.0])

    def g(x):
        return a0 - a @ np.asarray(x)

    indep = correlated_gaussian_reliability(mean, std, np.eye(2), g).beta
    pos = correlated_gaussian_reliability(mean, std, np.array([[1.0, 0.8], [0.8, 1.0]]), g).beta
    # positive correlation of like-signed loads inflates the variance of the sum
    # → lower β. The two must differ measurably.
    assert pos < indep - 1e-3


def test_lognormal_equivalent_correlation_closed_form():
    zi, zj = 0.3, 0.4
    rho_x = 0.6
    m = [Marginal("lognormal", 1.0, zi), Marginal("lognormal", 0.5, zj)]
    nataf = build_nataf(m, np.array([[1.0, rho_x], [rho_x, 1.0]]))
    c = np.sqrt((np.exp(zi * zi) - 1.0) * (np.exp(zj * zj) - 1.0))
    rho_z_expected = np.log(1.0 + rho_x * c) / (zi * zj)
    assert nataf.correlation_u[0, 1] == pytest.approx(rho_z_expected, rel=1e-12)
    # round-trip x→u→x through the correlated transform
    x = np.array([np.exp(1.2), np.exp(0.7)])
    assert np.allclose(nataf.u_to_x(nataf.x_to_u(x)), x, atol=1e-10)


def test_lognormal_marginal_round_trip():
    m = Marginal("lognormal", 0.8, 0.25)
    for x in (0.5, 1.0, 3.7, 12.0):
        assert m.from_standard_normal(m.to_standard_normal(x)) == pytest.approx(x, rel=1e-12)


def test_identity_correlation_reduces_to_standardize():
    mean = np.array([3.0, -1.0, 7.0])
    std = np.array([1.0, 2.0, 0.5])
    m = [Marginal("normal", mu, s) for mu, s in zip(mean, std, strict=True)]
    nataf = build_nataf(m)  # identity correlation
    x = np.array([4.0, 1.0, 6.0])
    assert np.allclose(nataf.x_to_u(x), standardize_gaussian(x, mean, std), atol=1e-12)


def test_nataf_contracts():
    m = [Marginal("normal", 0.0, 1.0), Marginal("normal", 0.0, 1.0)]
    with pytest.raises(SolverError, match="shape_mismatch"):
        build_nataf(m, np.eye(3))
    with pytest.raises(SolverError, match="not_symmetric"):
        build_nataf(m, np.array([[1.0, 0.5], [0.4, 1.0]]))
    with pytest.raises(SolverError, match="not_positive_definite"):
        build_nataf(m, np.array([[1.0, 1.5], [1.5, 1.0]]))
    with pytest.raises(SolverError, match="mixed_marginal"):
        build_nataf(
            [Marginal("normal", 0.0, 1.0), Marginal("lognormal", 0.0, 0.3)],
            np.array([[1.0, 0.5], [0.5, 1.0]]),
        )
