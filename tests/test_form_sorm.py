"""Wave II (v6): FORM / SORM + importance sampling.

Quantitative anchors:
- For a *linear* limit state g(u) = β₀ − aᵀu in standard-normal space, FORM is
  exact: β = β₀/‖a‖, P_f = Φ(−β), and HL-RF converges in a single step.
- SORM reduces to FORM when the limit state is linear (zero curvature), and
  bends P_f in the analytically-correct direction for a known parabola.
- Importance sampling at the MPP recovers the analytical P_f with a coefficient
  of variation far below crude Monte Carlo at the same sample count.
"""

from __future__ import annotations

from math import erf, sqrt

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    form_hlrf,
    importance_sampling,
    sorm_breitung,
    standardize_gaussian,
)


def _phi(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _linear_limit_state(a: np.ndarray, beta0: float):
    """g(u) = β₀ − aᵀu; failure = {aᵀu ≥ β₀}. True β = β₀/‖a‖."""
    a = np.asarray(a, dtype=float)
    return lambda u: float(beta0 - a @ np.asarray(u, dtype=float))


# --- FORM ------------------------------------------------------------------


def test_form_linear_exact_beta():
    a = np.array([3.0, 4.0])  # ‖a‖ = 5
    beta0 = 10.0
    res = form_hlrf(_linear_limit_state(a, beta0), n_vars=2)
    assert res.converged
    assert res.beta == pytest.approx(beta0 / 5.0, abs=1e-7)  # = 2.0
    assert res.p_failure == pytest.approx(_phi(-2.0), abs=1e-7)


def test_form_linear_converges_in_one_step():
    a = np.array([1.0, 0.0, 0.0])
    res = form_hlrf(_linear_limit_state(a, 3.0), n_vars=3)
    # HL-RF reaches the MPP on the first update for a linear g.
    assert res.n_iterations <= 2
    # MPP for g = 3 − u₀ is (3,0,0).
    assert np.allclose(res.mpp, [3.0, 0.0, 0.0], atol=1e-6)


def test_form_origin_unsafe_negative_beta():
    # β₀ < 0 → origin already fails → P_f > 0.5, β < 0.
    a = np.array([1.0, 0.0])
    res = form_hlrf(_linear_limit_state(a, -1.5), n_vars=2)
    assert res.beta < 0
    assert res.p_failure > 0.5
    assert res.p_failure == pytest.approx(_phi(1.5), abs=1e-6)


def test_form_rejects_bad_dimension():
    with pytest.raises(SolverError, match="n_vars_must_be_positive"):
        form_hlrf(lambda u: 1.0, n_vars=0)


# --- SORM ------------------------------------------------------------------


def test_sorm_reduces_to_form_for_linear():
    a = np.array([2.0, 1.0])
    g = _linear_limit_state(a, 4.0)
    form = form_hlrf(g, n_vars=2)
    sorm = sorm_breitung(g, form)
    assert sorm.p_failure == pytest.approx(form.p_failure, rel=1e-6)


def test_sorm_parabola_bends_pf_down():
    """g(u) = β₀ − u₂ + (κ/2)u₁² curves away from the origin (κ>0):
    the safe domain is convex there, so SORM gives a lower P_f than FORM, and
    matches Breitung's closed form Φ(−β)(1+βκ)^(−1/2)."""
    beta0, kappa = 2.5, 0.3

    def g(u):
        return float(beta0 - u[1] + 0.5 * kappa * u[0] ** 2)

    form = form_hlrf(g, n_vars=2)
    assert form.beta == pytest.approx(beta0, abs=1e-5)  # MPP = (0, β₀)
    sorm = sorm_breitung(g, form)
    breitung = _phi(-beta0) * (1.0 + beta0 * kappa) ** -0.5
    assert sorm.p_failure < form.p_failure  # convex safe domain → lower P_f
    assert sorm.p_failure == pytest.approx(breitung, rel=0.05)


# --- Importance sampling ---------------------------------------------------


def test_importance_sampling_matches_analytical():
    a = np.array([1.0, 0.0])
    beta0 = 3.0  # rare: P_f = Φ(−3) ≈ 1.35e-3
    g = _linear_limit_state(a, beta0)
    form = form_hlrf(g, n_vars=2)
    out = importance_sampling(g, n_vars=2, design_point=form.mpp, n_samples=4000, rng_seed=0)
    p_true = _phi(-beta0)
    assert out["p_failure"] == pytest.approx(p_true, rel=0.12)
    assert out["n_failures"] > 0


def test_importance_sampling_beats_crude_mc_variance():
    """At a rare-event β=3, IS has a much lower coefficient of variation than
    the analytical crude-MC cov = sqrt((1−P_f)/(N·P_f)) at the same N."""
    a = np.array([1.0, 0.0])
    beta0 = 3.0
    g = _linear_limit_state(a, beta0)
    form = form_hlrf(g, n_vars=2)
    n = 4000
    out = importance_sampling(g, n_vars=2, design_point=form.mpp, n_samples=n, rng_seed=1)
    p_true = _phi(-beta0)
    crude_cov = sqrt((1.0 - p_true) / (n * p_true))
    assert out["cov"] < 0.25 * crude_cov  # large variance reduction
    assert out["cov"] < 0.10


def test_importance_sampling_rejects_bad_samples():
    with pytest.raises(SolverError, match="n_samples_must_be_positive"):
        importance_sampling(lambda u: 1.0, n_vars=1, design_point=np.zeros(1), n_samples=0)


# --- helper ----------------------------------------------------------------


def test_standardize_gaussian_and_rejects_bad_std():
    u = standardize_gaussian([12.0, 8.0], mean=[10.0, 6.0], std=[2.0, 4.0])
    assert np.allclose(u, [1.0, 0.5])
    with pytest.raises(SolverError, match="nonpositive_std"):
        standardize_gaussian([1.0], mean=[0.0], std=[0.0])
