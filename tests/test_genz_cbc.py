"""Wave CCCCCCCC (v16, D116) — CBC deterministic vector wired into the Genz MVN CDF
estimator (closes D112's "wire CBC z into genz_mvn_cdf_lattice" reopening).

D086's genz_mvn_cdf_lattice uses a textbook Korobov vector under random shifts (statistical
std_error). This adds a deterministic CBC-lattice estimator: seed-free / byte-exact
reproducible, reporting the deterministic worst-case error certificate e(z). Quantitative
analytical anchors (deterministic reproduction; convergence to an independent Gauss–Hermite
reference; exact m=1), never qualitative trends.
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    _korobov_generating_vector,
    _standard_normal_cdf,
    cbc_korobov_generating_vector,
    genz_mvn_cdf_cbc,
    korobov_worst_case_error,
)

_B = np.array([1.5, 2.0, 1.0, 2.5])
_M = _B.size
_RHO = 0.4
_R = (1.0 - _RHO) * np.eye(_M) + _RHO * np.ones((_M, _M))


def _equicorr_ref(b, rho, n=48):
    """One-factor Gauss–Hermite reference for the equicorrelated MVN CDF:
    Φ_m(b;ρ) = ∫ φ(t) ∏_k Φ((b_k − √ρ t)/√(1−ρ)) dt."""
    x, wq = np.polynomial.hermite_e.hermegauss(n)
    tot = 0.0
    for t, wt in zip(x, wq, strict=True):
        p = np.prod([_standard_normal_cdf((bk - np.sqrt(rho) * t) / np.sqrt(1.0 - rho)) for bk in b])
        tot += wt * p
    return float(tot / np.sqrt(2.0 * np.pi))


def test_deterministic_seed_free_reproducible():
    """Headline: the CBC-lattice estimate is fully deterministic — two calls give a
    bit-identical value and generating vector (no RNG, no seed), unlike D086's lattice."""
    r1 = genz_mvn_cdf_cbc(_B, _R, n_points=1021)
    r2 = genz_mvn_cdf_cbc(_B, _R, n_points=1021)
    assert r1.value == r2.value
    assert np.array_equal(r1.generating_vector, r2.generating_vector)


def test_m1_is_exact():
    """m=1 (no integration dimension): returns Φ(b/√R) exactly with zero worst-case error."""
    r = genz_mvn_cdf_cbc(np.array([1.3]), np.array([[1.0]]), n_points=1021)
    assert r.value == _standard_normal_cdf(1.3)
    assert r.worst_case_error == 0.0


def test_converges_to_gauss_hermite_reference():
    """Convergence: refining N drives the deterministic estimate to an independent
    Gauss–Hermite equicorrelated reference (abs error shrinks below 5e-4 by N≈2039)."""
    ref = _equicorr_ref(_B, _RHO)
    err_lo = abs(genz_mvn_cdf_cbc(_B, _R, n_points=127).value - ref)
    err_hi = abs(genz_mvn_cdf_cbc(_B, _R, n_points=2039).value - ref)
    assert err_hi < err_lo  # refining N reduces the error
    assert err_hi < 5e-4


def test_uses_cbc_vector_and_reports_certificate():
    """The estimator uses the CBC generating vector and reports the deterministic e(z)
    certificate, which is ≤ the textbook Korobov vector's (CBC quality advantage)."""
    n = 1021
    r = genz_mvn_cdf_cbc(_B, _R, n_points=n)
    d = _M - 1
    gamma = 1.0 / (np.arange(1, d + 1, dtype=float) ** 2)
    assert np.array_equal(r.generating_vector, cbc_korobov_generating_vector(d, n, gamma))
    assert r.worst_case_error == pytest.approx(korobov_worst_case_error(r.generating_vector, n, gamma), abs=1e-15)
    e_korobov = korobov_worst_case_error(_korobov_generating_vector(d, 76, n), n, gamma)
    assert r.worst_case_error <= e_korobov + 1e-12


def test_worst_case_error_decreases_with_n():
    """The deterministic certificate e(z) decays as N grows (better rule)."""
    es = [genz_mvn_cdf_cbc(_B, _R, n_points=n).worst_case_error for n in (127, 521, 2039)]
    assert all(es[i] > es[i + 1] for i in range(len(es) - 1))


def test_genz_cbc_guards():
    """Guards: non-SPD R and too-few points raise SolverError."""
    bad = np.array([[1.0, 2.0], [2.0, 1.0]])  # not positive definite
    with pytest.raises(SolverError, match="genz_cbc_not_positive_definite"):
        genz_mvn_cdf_cbc(np.array([1.0, 1.0]), bad, n_points=257)
    with pytest.raises(SolverError, match="genz_cbc_too_few_points"):
        genz_mvn_cdf_cbc(_B, _R, n_points=1)
