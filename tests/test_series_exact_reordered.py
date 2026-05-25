"""Wave BBBBBB (v14, D099) — Genz reordering wired into system_reliability_series_exact.

Quantitative analytical anchors (bit-exact backward-compat / fixed-N variance reduction
vs exact reference), never qualitative trends. Traces D094's reopening criterion: "wire
reordering into system_reliability_series_exact so the production reliability path
benefits from the variance reduction".

INTEGRATION DISCIPLINE (v14): reorder=False (default) reproduces D078's exact path
bit-for-bit; reorder=True converges to the SAME P_f with smaller variance.
"""

from math import erf, sqrt

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    genz_mvn_cdf,
    system_reliability_series_exact,
    system_reliability_series_exact_reordered,
)

_BETAS = np.array([3.0, 2.5, 2.0, 1.0, 0.5, -0.2])  # wide spread ⟹ natural order is poor
_M = _BETAS.size
_RHO = 0.5
_R = np.full((_M, _M), _RHO)
np.fill_diagonal(_R, 1.0)

_PHI = np.vectorize(lambda x: 0.5 * (1.0 + erf(x / sqrt(2.0))), otypes=[float])


def _equicorr_series_pf(b, rho):
    """Exact series P_f = 1 − Φ_m(β; equicorr ρ) via the 1-factor 1-D reduction."""
    t = np.linspace(-12.0, 12.0, 8001)
    pdf = np.exp(-0.5 * t * t) / np.sqrt(2.0 * np.pi)
    prod = np.prod([_PHI((bi - np.sqrt(rho) * t) / np.sqrt(1.0 - rho)) for bi in b], axis=0)
    return 1.0 - float(np.trapezoid(pdf * prod, t))


def test_reorder_false_is_bit_exact_d078():
    """Backward-compat: reorder=False reproduces the D078 1−genz_mvn_cdf path exactly."""
    got = system_reliability_series_exact(_BETAS, _R, n_samples=20_000, seed=0)
    direct = 1.0 - genz_mvn_cdf(_BETAS, _R, n_samples=20_000, seed=0)
    assert got == direct  # identical code path ⟹ bit-exact
    # and equals the default-arg call (no param drift)
    assert got == system_reliability_series_exact(_BETAS, _R, n_samples=20_000, seed=0)


def test_reordered_converges_to_same_value():
    """High-N reordered and unordered series P_f agree (same estimand)."""
    hi_ord = system_reliability_series_exact(_BETAS, _R, n_samples=200_000, seed=1, reorder=True)
    hi_nat = system_reliability_series_exact(_BETAS, _R, n_samples=200_000, seed=1, reorder=False)
    assert hi_ord == pytest.approx(hi_nat, abs=3e-3)
    assert hi_ord == pytest.approx(_equicorr_series_pf(_BETAS, _RHO), abs=3e-3)


def test_reordering_cuts_fixed_sample_error_in_production_path():
    """The headline: reorder=True cuts fixed-N error several-fold in the production fn."""
    ref = _equicorr_series_pf(_BETAS, _RHO)
    err_nat = np.mean(
        [abs(system_reliability_series_exact(_BETAS, _R, n_samples=400, seed=s) - ref) for s in range(60)]
    )
    err_ord = np.mean(
        [
            abs(system_reliability_series_exact(_BETAS, _R, n_samples=400, seed=s, reorder=True) - ref)
            for s in range(60)
        ]
    )
    assert err_ord < 0.5 * err_nat  # measured ratio ≈ 0.11 (≈9× reduction)


def test_convenience_wrapper_equals_reorder_true():
    """system_reliability_series_exact_reordered == ...exact(reorder=True) bit-exact."""
    a = system_reliability_series_exact_reordered(_BETAS, _R, n_samples=5000, seed=2)
    b = system_reliability_series_exact(_BETAS, _R, n_samples=5000, seed=2, reorder=True)
    assert a == b


def test_independence_both_paths():
    """At R=I both paths give 1 − Π Φ(β_k)."""
    indep = 1.0 - float(np.prod(_PHI(_BETAS)))
    pf_nat = system_reliability_series_exact(_BETAS, np.eye(_M), n_samples=200_000, seed=0)
    pf_ord = system_reliability_series_exact_reordered(_BETAS, np.eye(_M), n_samples=200_000, seed=0)
    assert pf_nat == pytest.approx(indep, abs=2e-4)
    assert pf_ord == pytest.approx(indep, abs=2e-4)


def test_series_exact_reordered_guards():
    """Shape / empty-modes guards raise SolverError on both the param and the wrapper."""
    with pytest.raises(SolverError, match="system_reliability_correlation_shape"):
        system_reliability_series_exact(_BETAS, np.eye(3), reorder=True)
    with pytest.raises(SolverError, match="system_reliability_no_modes"):
        system_reliability_series_exact_reordered(np.array([]))
