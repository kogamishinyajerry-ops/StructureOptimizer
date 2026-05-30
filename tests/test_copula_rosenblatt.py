"""Wave NNN (v10, D069): Archimedean-copula Rosenblatt (Clayton / Frank).

Quantitative anchors (analytical, not qualitative trend):
- the Rosenblatt **conditional CDF round-trips** exactly: for both families
  ``conditional_ppf(u₁, conditional_cdf(u₁,u₂)) = u₂`` to ≤ 1e-9, and the full
  ``x → u → x`` / ``u → x → u`` transforms recover their input;
- **θ → 0 degenerates to independence**: the conditional CDF ``C_{2|1}(u₂|u₁) →
  u₂`` and ``C(u₁,u₂) → u₁·u₂`` as θ → 0 (vanishing dependence);
- **Kendall's τ matches the closed form**: Clayton ``θ/(θ+2)`` and Frank
  ``1−4/θ(1−D₁(θ))`` reproduce the empirical Kendall τ of conditional-method
  samples.

D061's reopening criterion: non-Gaussian Rosenblatt (Clayton/Frank copulas)
beyond the MVN-only transform.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    Marginal,
    build_copula_rosenblatt,
    clayton_copula,
    frank_copula,
)


def _empirical_kendall_tau(x: np.ndarray, y: np.ndarray) -> float:
    n = len(x)
    s = 0.0
    for i in range(n):
        s += float((np.sign(x[i] - x[i + 1 :]) * np.sign(y[i] - y[i + 1 :])).sum())
    return 2.0 * s / (n * (n - 1))


def _sample_copula(copula, n, seed):
    rng = np.random.default_rng(seed)
    u1 = rng.uniform(0.0, 1.0, n)
    w = rng.uniform(0.0, 1.0, n)
    u2 = np.array([copula.conditional_ppf(a, b) for a, b in zip(u1, w, strict=True)])
    return u1, u2


@pytest.mark.parametrize("copula", [clayton_copula(4.0), frank_copula(5.0)])
def test_conditional_cdf_round_trip(copula):
    rng = np.random.default_rng(0)
    max_err = 0.0
    for _ in range(2000):
        u1, u2 = rng.uniform(0.01, 0.99, 2)
        w = copula.conditional_cdf(u1, u2)
        u2_back = copula.conditional_ppf(u1, w)
        max_err = max(max_err, abs(u2 - u2_back))
    assert max_err <= 1e-9, f"{copula.family} conditional round-trip err {max_err:.2e}"


@pytest.mark.parametrize("copula", [clayton_copula(3.0), frank_copula(6.0)])
def test_full_transform_round_trip(copula):
    marginals = [Marginal("normal", 10.0, 2.0), Marginal("lognormal", 0.5, 0.3)]
    rb = build_copula_rosenblatt(marginals, copula)
    rng = np.random.default_rng(1)
    for _ in range(200):
        z = rng.normal(0.0, 1.0, 2)
        x = rb.u_to_x(z)
        z_back = rb.x_to_u(x)
        assert np.allclose(z, z_back, atol=1e-7), f"{copula.family} u→x→u: {z} vs {z_back}"


def test_theta_to_zero_degenerates_to_independence():
    # conditional CDF → u₂ and C(u₁,u₂) → u₁·u₂ as θ → 0
    for theta in (0.5, 0.1, 0.01):
        for fam in (clayton_copula(theta), frank_copula(theta)):
            cond = fam.conditional_cdf(0.3, 0.7)
            cdf = fam.cdf(0.3, 0.7)
            # error shrinks (roughly linearly) with θ
            assert abs(cond - 0.7) <= 2.0 * theta, f"{fam.family} cond {cond:.4f} not → u₂ at θ={theta}"
            assert abs(cdf - 0.21) <= 2.0 * theta, f"{fam.family} cdf {cdf:.4f} not → u₁u₂ at θ={theta}"


def test_kendall_tau_clayton_closed_form():
    for theta in (1.0, 4.0, 8.0):
        cop = clayton_copula(theta)
        assert abs(cop.kendall_tau() - theta / (theta + 2.0)) < 1e-12  # closed form
        u1, u2 = _sample_copula(cop, 1500, seed=2)
        tau_emp = _empirical_kendall_tau(u1, u2)
        assert abs(tau_emp - cop.kendall_tau()) < 0.03, f"τ θ={theta}: emp {tau_emp:.3f} vs {cop.kendall_tau():.3f}"


def test_kendall_tau_frank_closed_form():
    for theta in (3.0, 6.0):
        cop = frank_copula(theta)
        u1, u2 = _sample_copula(cop, 1500, seed=3)
        tau_emp = _empirical_kendall_tau(u1, u2)
        assert abs(tau_emp - cop.kendall_tau()) < 0.03, f"τ θ={theta}: emp {tau_emp:.3f} vs {cop.kendall_tau():.3f}"


def test_copula_input_guards():
    with pytest.raises(SolverError):
        clayton_copula(-1.0)  # clayton needs θ>0
    with pytest.raises(SolverError):
        frank_copula(0.0)  # frank needs θ≠0
    with pytest.raises(SolverError):
        from structure_optimizer.core.reliability import ArchimedeanCopula

        ArchimedeanCopula("gumbel_copula", 2.0)  # unknown family
    with pytest.raises(SolverError):
        build_copula_rosenblatt([Marginal("normal", 0.0, 1.0)], clayton_copula(2.0))  # needs 2 marginals


def test_copula_rosenblatt_drives_form():
    # the transform plugs into FORM via wrap_limit_state (same interface as
    # the Gaussian Rosenblatt) — sanity that a reliability index comes out finite
    from structure_optimizer.core.reliability import form_hlrf

    marginals = [Marginal("normal", 5.0, 1.0), Marginal("normal", 5.0, 1.0)]
    rb = build_copula_rosenblatt(marginals, clayton_copula(2.0))

    def g(x):  # capacity 8 minus the sum of two demands
        return 16.0 - x[0] - x[1]

    res = form_hlrf(rb.wrap_limit_state(g), n_vars=2)
    assert np.isfinite(res.beta)
    assert 0.0 < res.p_failure < 1.0
