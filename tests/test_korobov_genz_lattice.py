"""Wave EEEE (v12, D086): randomly-shifted Korobov-lattice Genz MVN CDF + SE.

Quantitative anchors (high-accuracy reference + convergence, not qualitative):
- **degenerates to exact** on the independent case (Φ_m = ∏Φ(b_i), closed form) and
  matches the equicorrelation reference (a 1-D Gauss-Hermite reduction, exact to
  quadrature) to within the reported standard error;
- **faster than plain MC**: at equal sample budget the lattice RMS error (vs the
  exact reference) is several× smaller than D078's pseudo-random Genz MC;
- **the reported standard error is a genuine error estimate**: |value − exact| is
  bracketed by ~3·SE across seeds, and SE shrinks as n_points grows;
- determinism; guards.

D078's reopening criterion: "randomised-lattice (Korobov) Genz with error bounds".
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.polynomial.hermite_e import hermegauss
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    _standard_normal_cdf,
    genz_mvn_cdf,
    genz_mvn_cdf_lattice,
    system_reliability_series_lattice,
)


def _equicorrelation_exact(b: np.ndarray, rho: float) -> float:
    """Exact Φ_m(b; R) for R = (1−ρ)I + ρ·11ᵀ via the 1-D reduction
    Φ_m = ∫ ∏_i Φ((b_i + √ρ·t)/√(1−ρ)) φ(t) dt, by Gauss-Hermite quadrature."""
    nodes, wts = hermegauss(120)  # probabilists' weight e^{-t²/2}
    wts = wts / np.sqrt(2.0 * np.pi)
    s = 0.0
    for t, wt in zip(nodes, wts, strict=True):
        prod = np.prod([_standard_normal_cdf((b[i] + np.sqrt(rho) * t) / np.sqrt(1.0 - rho)) for i in range(b.size)])
        s += wt * prod
    return float(s)


def _equicorr(m: int, rho: float) -> np.ndarray:
    return (1.0 - rho) * np.eye(m) + rho * np.ones((m, m))


def test_independent_case_is_exact_product():
    b = np.array([0.5, 1.0, 1.5])
    R = np.eye(3)
    exact = float(np.prod([_standard_normal_cdf(x) for x in b]))
    res = genz_mvn_cdf_lattice(b, R, n_points=521, n_shifts=8)
    # independent ⟹ integrand is constant ⟹ estimator exact for any points
    assert abs(res.value - exact) <= 1e-9


def test_matches_equicorrelation_reference_within_se():
    b = np.ones(4)
    rho = 0.5
    exact = _equicorrelation_exact(b, rho)
    res = genz_mvn_cdf_lattice(b, _equicorr(4, rho), n_points=1021, n_shifts=16, seed=0)
    assert abs(res.value - exact) <= 4.0 * res.std_error + 1e-6, f"{res.value} vs {exact}, SE {res.std_error}"
    assert res.std_error < 1e-3


def test_lattice_beats_plain_monte_carlo_at_equal_budget():
    """RMS error over seeds: the Korobov lattice is several× more accurate than the
    pseudo-random Genz MC at the same total sample count."""
    b = np.ones(4)
    rho = 0.5
    R = _equicorr(4, rho)
    exact = _equicorrelation_exact(b, rho)
    n_points, n_shifts = 1021, 1
    budget = n_points * n_shifts
    lat_err, mc_err = [], []
    for s in range(20):
        lat = genz_mvn_cdf_lattice(b, R, n_points=n_points, n_shifts=2, seed=s).value
        mc = genz_mvn_cdf(b, R, n_samples=2 * budget, seed=s)
        lat_err.append(lat - exact)
        mc_err.append(mc - exact)
    rms_lat = float(np.sqrt(np.mean(np.square(lat_err))))
    rms_mc = float(np.sqrt(np.mean(np.square(mc_err))))
    assert rms_lat < rms_mc / 3.0, f"lattice RMS {rms_lat:.2e} not < MC RMS {rms_mc:.2e}/3"


def test_standard_error_brackets_true_error_and_shrinks():
    b = np.ones(4)
    rho = 0.5
    R = _equicorr(4, rho)
    exact = _equicorrelation_exact(b, rho)
    # SE brackets the true error in the large majority of seeds
    bracketed = 0
    for s in range(30):
        res = genz_mvn_cdf_lattice(b, R, n_points=1021, n_shifts=12, seed=s)
        if abs(res.value - exact) <= 3.0 * res.std_error:
            bracketed += 1
    assert bracketed >= 27, f"only {bracketed}/30 within 3·SE"
    # SE shrinks as the lattice grows
    se_small = genz_mvn_cdf_lattice(b, R, n_points=251, n_shifts=16, seed=0).std_error
    se_large = genz_mvn_cdf_lattice(b, R, n_points=2039, n_shifts=16, a=1487, seed=0).std_error
    assert se_large < se_small


def test_system_reliability_lattice_reports_se():
    betas = np.array([2.5, 3.0, 2.8])
    rho = 0.4
    R = _equicorr(3, rho)
    pf, se = system_reliability_series_lattice(betas, R, n_points=1021, n_shifts=12)
    # P_f = 1 − Φ_m(β); cross-check value against the exact equicorrelation reference
    exact_safe = _equicorrelation_exact(betas, rho)
    assert abs((1.0 - pf) - exact_safe) <= 4.0 * se + 1e-6
    assert 0.0 <= pf <= 1.0 and se >= 0.0


def test_determinism_and_guards():
    b = np.ones(3)
    R = _equicorr(3, 0.3)
    a = genz_mvn_cdf_lattice(b, R, n_points=521, n_shifts=8, seed=7)
    c = genz_mvn_cdf_lattice(b, R, n_points=521, n_shifts=8, seed=7)
    assert a.value == c.value and a.std_error == c.std_error
    with pytest.raises(SolverError, match="needs_two_shifts"):
        genz_mvn_cdf_lattice(b, R, n_points=521, n_shifts=1)
    with pytest.raises(SolverError, match="too_few_points"):
        genz_mvn_cdf_lattice(b, R, n_points=1, n_shifts=4)
    with pytest.raises(SolverError, match="not_positive_definite"):
        genz_mvn_cdf_lattice(b, np.array([[1.0, 2.0, 0.0], [2.0, 1.0, 0.0], [0.0, 0.0, 1.0]]), n_shifts=4)
