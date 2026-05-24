"""Wave ZZ (v8, D055): system reliability — series systems + Ditlevsen bounds.

Quantitative anchors:
- the bivariate-normal CDF matches its exact special cases (ρ=0 product,
  the Φ₂(0,0;ρ) = ¼ + arcsin(ρ)/2π closed form, ρ→1 → min);
- a single-mode series system equals Φ(−β); an independent multi-mode series
  failure probability lies within the Ditlevsen bounds, which are tighter than
  the simple unimodal bounds;
- positive correlation between failure modes lowers the series failure
  probability (overlapping modes).
"""

from __future__ import annotations

from math import asin, erf, pi, sqrt

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    bivariate_normal_cdf,
    system_reliability_parallel,
    system_reliability_series,
)


def _phi(x):
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def test_bivariate_normal_cdf_special_cases():
    # ρ=0 → product of marginals
    assert bivariate_normal_cdf(0.5, -0.3, 0.0) == pytest.approx(_phi(0.5) * _phi(-0.3), abs=1e-12)
    # Φ₂(0,0;ρ) = 1/4 + arcsin(ρ)/(2π)
    for rho in (0.3, 0.6, -0.5, 0.9):
        assert bivariate_normal_cdf(0.0, 0.0, rho) == pytest.approx(0.25 + asin(rho) / (2.0 * pi), abs=1e-7)
    # ρ→1 → min(Φ(a), Φ(b))
    assert bivariate_normal_cdf(1.0, 2.0, 1.0) == pytest.approx(min(_phi(1.0), _phi(2.0)), abs=1e-4)


def test_single_mode_series_equals_phi():
    r = system_reliability_series([2.0])
    assert r["p_failure_lower"] == pytest.approx(_phi(-2.0), abs=1e-12)
    assert r["p_failure_upper"] == pytest.approx(_phi(-2.0), abs=1e-12)


def test_independent_series_within_ditlevsen_bounds():
    betas = [2.0, 2.5, 3.0]
    p = [_phi(-b) for b in betas]
    exact = 1.0 - np.prod([1.0 - pi_ for pi_ in p])  # independent series failure
    r = system_reliability_series(betas)  # identity correlation
    assert r["p_failure_lower"] - 1e-9 <= exact <= r["p_failure_upper"] + 1e-9
    # Ditlevsen bounds are within (tighter than) the simple unimodal bounds
    assert r["simple_lower"] <= r["p_failure_lower"] <= r["p_failure_upper"] <= r["simple_upper"] + 1e-9


def test_positive_correlation_lowers_series_failure():
    betas = [2.0, 2.5, 3.0]
    indep = system_reliability_series(betas)
    rho = np.full((3, 3), 0.8)
    np.fill_diagonal(rho, 1.0)
    corr = system_reliability_series(betas, rho)
    # overlapping (correlated) failure modes → lower total series failure
    assert corr["p_failure_upper"] < indep["p_failure_lower"]


def test_parallel_independent_is_product():
    assert system_reliability_parallel(2.0, 2.5, 0.0) == pytest.approx(_phi(-2.0) * _phi(-2.5), abs=1e-10)
    # perfectly correlated parallel → min (both fail together)
    assert system_reliability_parallel(2.0, 2.5, 1.0) == pytest.approx(min(_phi(-2.0), _phi(-2.5)), abs=1e-4)


def test_contracts():
    with pytest.raises(SolverError, match="bvn_rho_out_of_range"):
        bivariate_normal_cdf(0.0, 0.0, 1.5)
    with pytest.raises(SolverError, match="no_modes"):
        system_reliability_series([])
    with pytest.raises(SolverError, match="correlation_shape"):
        system_reliability_series([1.0, 2.0], np.eye(3))
