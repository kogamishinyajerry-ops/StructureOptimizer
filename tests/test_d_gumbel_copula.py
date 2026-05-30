"""Wave DDDDD (v13, D093) — d-dim exchangeable Gumbel copula.

Quantitative analytical anchors (closed form / numerical-mixed-partial round-trip),
never qualitative trends. Traces D085's reopening criterion: "a non-Clayton d-dim
copula (e.g. exchangeable Gumbel) with a closed-form conditional CDF".

The Gumbel inverse generator ψ(s)=exp(−s^{1/θ}) has no one-line k-th derivative, so the
conditional CDF is built from the EXACT recursion ψ^{(k)}=ψ·g_k. We verify it against
finite-difference mixed partials of the CDF, against the bivariate closed form at d=2,
and via a conditional-ppf round-trip. Kendall τ=1−1/θ is exact.
"""

import itertools

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import gumbel_copula, gumbel_d_copula

THETA = 2.2  # ⟹ Kendall τ = 1 − 1/2.2 = 6/11


def _numerical_mixed_conditional(u: np.ndarray, theta: float, h: float = 1e-4) -> float:
    """Rosenblatt conditional C_{k|1..k-1} via central-difference mixed partials of the
    copula CDF over the first k−1 coordinates (independent cross-check)."""
    u = np.asarray(u, dtype=float)
    k = u.shape[0]
    cop = gumbel_d_copula(k, theta)

    def mixed(full_fn) -> float:
        s = 0.0
        for signs in itertools.product([1, -1], repeat=k - 1):
            xx = u.copy()
            for i, sg in enumerate(signs):
                xx[i] += sg * h
            s += np.prod(signs) * full_fn(xx)
        return s / (2 * h) ** (k - 1)

    num = mixed(lambda x: cop.cdf(x))  # ∂^{k-1} C(u_1..u_k)
    # denominator: same mixed partial of the (k−1)-margin C(u_1..u_{k-1}) ≡ set u_k→1
    num_den = mixed(lambda x: cop.cdf(np.concatenate([x[: k - 1], [1.0 - 1e-12]])))
    return num / num_den


def test_cdf_closed_form_and_d2_degenerates_to_bivariate():
    """d=2 CDF equals the bivariate Gumbel; d=3 matches the explicit Archimedean form."""
    g2 = gumbel_d_copula(2, THETA)
    biv = gumbel_copula(THETA)
    assert g2.cdf([0.35, 0.62]) == pytest.approx(biv.cdf(0.35, 0.62), rel=1e-12)
    # d=3 explicit: exp(−(Σ(−ln u_i)^θ)^{1/θ})
    u = np.array([0.3, 0.5, 0.7])
    expect = np.exp(-((np.sum((-np.log(u)) ** THETA)) ** (1.0 / THETA)))
    assert gumbel_d_copula(3, THETA).cdf(u) == pytest.approx(expect, rel=1e-12)


def test_conditional_cdf_matches_numerical_mixed_partials():
    """The headline: the analytic conditional CDF equals FD mixed partials of the CDF."""
    g3 = gumbel_d_copula(3, THETA)
    u3 = np.array([0.3, 0.5, 0.7])
    assert g3.conditional_cdf(u3) == pytest.approx(_numerical_mixed_conditional(u3, THETA), abs=1e-7)
    g4 = gumbel_d_copula(4, THETA)
    u4 = np.array([0.2, 0.4, 0.6, 0.8])
    # 4th-order central FD is noisier; the analytic form is exact, FD is the approximation
    assert g4.conditional_cdf(u4) == pytest.approx(_numerical_mixed_conditional(u4, THETA), abs=1e-4)


def test_conditional_cdf_d2_degenerates_to_bivariate():
    """d=2 conditional CDF reproduces the bivariate Gumbel h-function exactly."""
    g2 = gumbel_d_copula(2, THETA)
    biv = gumbel_copula(THETA)
    for u1, u2 in [(0.2, 0.8), (0.5, 0.5), (0.35, 0.62), (0.9, 0.1)]:
        assert g2.conditional_cdf([u1, u2]) == pytest.approx(biv.conditional_cdf(u1, u2), abs=1e-12)


def test_kendall_tau_one_minus_inv_theta():
    """Pairwise Kendall τ = 1 − 1/θ, matching the bivariate copula's closed form."""
    for theta in (1.0, 1.5, 2.2, 5.0):
        g = gumbel_d_copula(4, theta)
        assert g.kendall_tau() == pytest.approx(1.0 - 1.0 / theta, rel=1e-14)
        assert g.kendall_tau() == pytest.approx(gumbel_copula(theta).kendall_tau(), rel=1e-12)


def test_conditional_ppf_round_trip_and_monotone():
    """conditional_ppf inverts conditional_cdf, and the conditional is monotone in u_k."""
    g3 = gumbel_d_copula(3, THETA)
    u_prev = np.array([0.4, 0.55])
    for w in (0.1, 0.5, 0.73, 0.95):
        uk = g3.conditional_ppf(u_prev, w, 3)
        back = g3.conditional_cdf(np.concatenate([u_prev, [uk]]))
        assert back == pytest.approx(w, abs=1e-9)
    # strictly increasing in u_k ⟹ a valid (invertible) conditional CDF
    xs = np.linspace(0.05, 0.95, 9)
    cc = [g3.conditional_cdf(np.array([0.4, 0.55, x])) for x in xs]
    assert all(cc[i] < cc[i + 1] for i in range(len(cc) - 1))


def test_gumbel_d_guards():
    """Dimension and θ guards raise single-string SolverError."""
    with pytest.raises(SolverError, match="gumbel_d_copula_dim_too_small"):
        gumbel_d_copula(1, THETA)
    with pytest.raises(SolverError, match="copula_gumbel_theta_below_one"):
        gumbel_d_copula(3, 0.5)
    with pytest.raises(SolverError, match="gumbel_d_copula_dim_mismatch"):
        gumbel_d_copula(3, THETA).cdf([0.1, 0.2])
    with pytest.raises(SolverError, match="gumbel_d_conditional_bad_k"):
        gumbel_d_copula(3, THETA).conditional_cdf([0.5])
