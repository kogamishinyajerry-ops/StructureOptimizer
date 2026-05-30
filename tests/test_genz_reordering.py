"""Wave EEEEE (v13, D094) — Genz variable reordering (priority ordering).

Quantitative analytical anchors (exact 1-D reference / fixed-N error ratio), never
qualitative trends. Traces D086's reopening criterion: "variable reordering by
integration-range width for faster Genz convergence".

The Genz separation-of-variables estimator's variance depends on the order in which
the integration axes are handled. Genz–Bretz **prioritisation** orders the
most-constrained (smallest expected probability) axes first. We verify it (a) converges
to the SAME value as the unordered estimator and the exact equicorrelation reference,
and (b) at a fixed small sample size has several-fold smaller error on a poorly-ordered
problem.
"""

from math import erf, sqrt

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    _genz_reorder_cholesky,
    genz_mvn_cdf,
    genz_mvn_cdf_reordered,
)

_PHI = np.vectorize(lambda x: 0.5 * (1.0 + erf(x / sqrt(2.0))), otypes=[float])


def _equicorr_mvn_cdf(b: np.ndarray, rho: float) -> float:
    """Exact Φ_m(b; equicorr ρ) via the 1-factor 1-D reduction
    ∫ φ(t) Π_i Φ((b_i − √ρ t)/√(1−ρ)) dt — fine-grid trapezoid ≈ machine reference."""
    b = np.asarray(b, dtype=float)
    t = np.linspace(-12.0, 12.0, 8001)
    pdf = np.exp(-0.5 * t * t) / np.sqrt(2.0 * np.pi)
    prod = np.prod([_PHI((bi - np.sqrt(rho) * t) / np.sqrt(1.0 - rho)) for bi in b], axis=0)
    return float(np.trapezoid(pdf * prod, t))


# A deliberately badly-ordered equicorrelated problem: large bounds (dominant mass)
# come FIRST in the natural order, so the unordered estimator integrates the
# high-variance axes last.
_RHO = 0.5
_B = np.array([3.0, 2.5, 2.0, 1.0, 0.0, -0.5])
_M = _B.size
_R = np.full((_M, _M), _RHO)
np.fill_diagonal(_R, 1.0)


def test_reordered_converges_to_exact_reference():
    """High-N reordered estimate matches the exact equicorrelation 1-D reference."""
    ref = _equicorr_mvn_cdf(_B, _RHO)
    got = genz_mvn_cdf_reordered(_B, _R, n_samples=200_000, seed=1)
    assert got == pytest.approx(ref, abs=2e-3)


def test_reordering_is_a_relabelling_same_value_as_unordered():
    """Reordered and unordered converge to the SAME value (reordering ≠ different answer)."""
    hi_ord = genz_mvn_cdf_reordered(_B, _R, n_samples=200_000, seed=1)
    hi_nat = genz_mvn_cdf(_B, _R, n_samples=200_000, seed=1)
    assert hi_ord == pytest.approx(hi_nat, abs=3e-3)


def test_reordering_cuts_fixed_sample_error_severalfold():
    """The headline: at a fixed small N the reordered error is several-fold smaller."""
    ref = _equicorr_mvn_cdf(_B, _RHO)
    err_nat = np.mean([abs(genz_mvn_cdf(_B, _R, n_samples=400, seed=s) - ref) for s in range(60)])
    err_ord = np.mean([abs(genz_mvn_cdf_reordered(_B, _R, n_samples=400, seed=s) - ref) for s in range(60)])
    # measured ratio ≈ 0.11 (≈9× error reduction); assert a safe < 0.5 (≥2× better)
    assert err_ord < 0.5 * err_nat


def test_priority_order_places_smallest_mass_first():
    """For equicorrelation the priority order sorts bounds ascending (smallest mass first)."""
    b_ord, _, perm = _genz_reorder_cholesky(_B, _R)
    assert np.all(np.diff(b_ord) >= -1e-12)  # non-decreasing bounds
    assert perm.tolist() == sorted(range(_M), key=lambda i: _B[i])


def test_full_correlation_matrix_correctness():
    """On a full (non-equicorrelation) SPD R, reordered and unordered high-N agree."""
    rng = np.random.default_rng(7)
    a = rng.normal(size=(5, 5))
    cov = a @ a.T
    d = np.sqrt(np.diag(cov))
    R = cov / np.outer(d, d)  # a genuine full correlation matrix
    b = np.array([0.5, 1.2, -0.3, 2.0, 0.8])
    hi_ord = genz_mvn_cdf_reordered(b, R, n_samples=300_000, seed=3)
    hi_nat = genz_mvn_cdf(b, R, n_samples=300_000, seed=3)
    assert hi_ord == pytest.approx(hi_nat, abs=4e-3)


def test_reorder_edge_cases_and_guards():
    """m=1 closed form, determinism, and shape / non-SPD guards."""
    assert genz_mvn_cdf_reordered(np.array([1.3]), np.array([[1.0]])) == pytest.approx(
        float(_PHI(np.array([1.3]))[0]), rel=1e-12
    )
    # determinism: same seed ⟹ identical
    v1 = genz_mvn_cdf_reordered(_B, _R, n_samples=1000, seed=42)
    v2 = genz_mvn_cdf_reordered(_B, _R, n_samples=1000, seed=42)
    assert v1 == v2
    with pytest.raises(SolverError, match="genz_mvn_correlation_shape"):
        genz_mvn_cdf_reordered(_B, np.eye(3))
    with pytest.raises(SolverError, match="genz_mvn_not_positive_definite"):
        genz_mvn_cdf_reordered(np.array([0.0, 0.0]), np.array([[1.0, 1.5], [1.5, 1.0]]))
