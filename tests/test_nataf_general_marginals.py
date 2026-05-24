"""Wave XX (v8, D053): general-marginal Nataf via Gauss-Hermite quadrature.

Quantitative anchors:
- the Gauss-Hermite Nataf integral reproduces D045's lognormal–lognormal
  closed-form equivalent correlation (the cross-check that the quadrature is
  correct);
- Weibull/Gumbel moments match their analytic formulas and the marginal
  transforms round-trip;
- the equivalent correlation vanishes at ρ_x=0 and is monotone in ρ_x; a general
  (Weibull+Gumbel) Nataf round-trips x→u→x.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    Marginal,
    build_nataf_general,
    nataf_correlation_gauss_hermite,
)


def test_gauss_hermite_matches_lognormal_closed_form():
    zi, zj = 0.3, 0.4
    mi, mj = Marginal("lognormal", 1.0, zi), Marginal("lognormal", 0.5, zj)
    for rho_x in (0.2, 0.6, -0.4):
        gh = nataf_correlation_gauss_hermite(mi, mj, rho_x, n_nodes=24)
        c = np.sqrt((np.exp(zi * zi) - 1.0) * (np.exp(zj * zj) - 1.0))
        closed = np.log(1.0 + rho_x * c) / (zi * zj)
        assert gh == pytest.approx(closed, abs=1e-6)


def test_weibull_moments_and_exponential_special_case():
    # exponential = Weibull(k=1, λ): mean = std = λ
    e = Marginal("weibull", 1.0, 5.0)
    assert e.moments()[0] == pytest.approx(5.0, rel=1e-9)
    assert e.moments()[1] == pytest.approx(5.0, rel=1e-9)
    # Rayleigh-ish Weibull(2, 3): mean = 3·Γ(1.5)
    from math import gamma

    w = Marginal("weibull", 2.0, 3.0)
    assert w.moments()[0] == pytest.approx(3.0 * gamma(1.5), rel=1e-9)


def test_gumbel_moments():
    g = Marginal("gumbel", 0.0, 1.0)
    assert g.moments()[0] == pytest.approx(0.5772156649, abs=1e-6)  # μ + βγ
    assert g.moments()[1] == pytest.approx(np.pi / np.sqrt(6.0), rel=1e-9)  # βπ/√6


def test_general_marginal_round_trips():
    for m, x in [
        (Marginal("weibull", 2.0, 3.0), 2.5),
        (Marginal("gumbel", 1.0, 0.5), 1.4),
        (Marginal("weibull", 1.5, 4.0), 6.0),
    ]:
        assert m.from_standard_normal(m.to_standard_normal(x)) == pytest.approx(x, rel=1e-9)


def test_equivalent_correlation_zero_and_monotone():
    w, g = Marginal("weibull", 2.0, 3.0), Marginal("gumbel", 1.0, 0.5)
    assert nataf_correlation_gauss_hermite(w, g, 0.0) == 0.0
    r_lo = nataf_correlation_gauss_hermite(w, g, 0.3)
    r_hi = nataf_correlation_gauss_hermite(w, g, 0.6)
    assert r_lo < r_hi
    # equivalent normal correlation is at least as large in magnitude as physical
    assert abs(r_hi) >= 0.6 - 1e-9


def test_build_nataf_general_round_trip():
    m = [Marginal("weibull", 2.0, 3.0), Marginal("gumbel", 1.0, 0.5)]
    nataf = build_nataf_general(m, np.array([[1.0, 0.4], [0.4, 1.0]]))
    x = np.array([3.2, 1.4])
    assert np.allclose(nataf.u_to_x(nataf.x_to_u(x)), x, atol=1e-8)


def test_contracts():
    w, g = Marginal("weibull", 2.0, 3.0), Marginal("gumbel", 1.0, 0.5)
    with pytest.raises(SolverError, match="rho_out_of_range"):
        nataf_correlation_gauss_hermite(w, g, 1.5)
    with pytest.raises(SolverError, match="unknown_marginal"):
        Marginal("cauchy", 0.0, 1.0)
    with pytest.raises(SolverError, match="nonpositive_scale"):
        Marginal("weibull", -1.0, 3.0)
