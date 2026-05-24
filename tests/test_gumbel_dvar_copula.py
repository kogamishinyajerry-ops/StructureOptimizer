"""Wave VVV (v11, D077): Gumbel copula + d-dimensional exchangeable Clayton.

Quantitative anchors (closed-form / numerical-derivative, not qualitative trend):
- **Gumbel conditional round-trip + derivative check**: the Gumbel conditional CDF
  ``C_{2|1}=∂C/∂u₁`` matches numerical ∂C/∂u₁ to ≤ 1e-6, its bisection inverse
  round-trips to ≤ 1e-9, and Kendall's τ = 1 − 1/θ in closed form;
- **d-dim Clayton conditional = true Rosenblatt conditional**: the closed-form
  ``C_{k|1..k-1}`` matches the numerical ratio of mixed partial derivatives of the
  copula CDF (≤ 1e-5);
- **d-dim Clayton Rosenblatt round-trip**: ``z → x → z`` to ≤ 1e-9 for d = 3, 4;
- **correct dependence**: samples generated through the transform recover the
  theoretical pairwise Kendall's τ = θ/(θ+2).

D069's reopening criterion: "d-dimensional / Gumbel copulas".
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    Marginal,
    build_clayton_rosenblatt,
    clayton_d_copula,
    gumbel_copula,
)


def test_gumbel_conditional_derivative_roundtrip_and_tau():
    th = 2.3
    g = gumbel_copula(th)
    h = 1e-6
    for u1, u2 in [(0.3, 0.5), (0.7, 0.2), (0.5, 0.9)]:
        # conditional CDF == numerical ∂C/∂u₁
        num = (g.cdf(u1 + h, u2) - g.cdf(u1 - h, u2)) / (2.0 * h)
        closed = g.conditional_cdf(u1, u2)
        assert abs(num - closed) <= 1e-6, f"u=({u1},{u2}) num {num} vs closed {closed}"
        # bisection inverse round-trips
        u2_back = g.conditional_ppf(u1, closed)
        assert abs(u2_back - u2) <= 1e-9
    # closed-form Kendall's τ
    assert abs(g.kendall_tau() - (1.0 - 1.0 / th)) < 1e-12


def test_gumbel_theta_below_one_raises():
    with pytest.raises(SolverError):
        gumbel_copula(0.5)


def test_clayton_d_conditional_matches_mixed_partials():
    th = 1.7
    c3 = clayton_d_copula(3, th)
    c2 = clayton_d_copula(2, th)
    h = 1e-5
    u1, u2, u3 = 0.4, 0.6, 0.3

    def d2(cop, a, b, *rest):
        return (
            cop.cdf([a + h, b + h, *rest])
            - cop.cdf([a + h, b - h, *rest])
            - cop.cdf([a - h, b + h, *rest])
            + cop.cdf([a - h, b - h, *rest])
        ) / (4.0 * h * h)

    # C_{3|1,2}(u3|u1,u2) = ∂²C₃/∂u₁∂u₂  /  ∂²C₂/∂u₁∂u₂
    num = d2(c3, u1, u2, u3) / (
        (c2.cdf([u1 + h, u2 + h]) - c2.cdf([u1 + h, u2 - h]) - c2.cdf([u1 - h, u2 + h]) + c2.cdf([u1 - h, u2 - h]))
        / (4.0 * h * h)
    )
    closed = c3.conditional_cdf([u1, u2, u3])
    assert abs(num - closed) / abs(num) <= 1e-5, f"num {num} vs closed {closed}"


def test_clayton_d_rosenblatt_roundtrip():
    for d in (3, 4):
        marg = [Marginal("normal", 0.0, 1.0) for _ in range(d)]
        tr = build_clayton_rosenblatt(marg, theta=1.7)
        assert tr.n_vars == d
        rng = np.random.default_rng(d)
        z = rng.standard_normal(d)
        x = tr.u_to_x(z)
        z2 = tr.x_to_u(x)
        assert np.max(np.abs(z - z2)) <= 1e-9


def test_clayton_d_recovers_kendall_tau():
    th = 1.7
    d = 3
    marg = [Marginal("normal", 0.0, 1.0) for _ in range(d)]
    tr = build_clayton_rosenblatt(marg, theta=th)
    tau_th = th / (th + 2.0)
    assert abs(clayton_d_copula(d, th).kendall_tau() - tau_th) < 1e-12

    rng = np.random.default_rng(0)
    n = 3000
    samples = np.array([tr.u_to_x(rng.standard_normal(d)) for _ in range(n)])

    def kendall_tau_emp(a, b):
        sa = np.sign(a[:, None] - a[None, :])
        sb = np.sign(b[:, None] - b[None, :])
        iu = np.triu_indices(len(a), 1)
        return float((sa * sb)[iu].mean())

    for i, j in [(0, 1), (0, 2), (1, 2)]:
        assert abs(kendall_tau_emp(samples[:, i], samples[:, j]) - tau_th) <= 0.04


def test_clayton_d_copula_error_handling():
    with pytest.raises(SolverError):
        clayton_d_copula(1, 1.7)  # dim too small
    with pytest.raises(SolverError):
        clayton_d_copula(3, -0.5)  # nonpositive theta
    with pytest.raises(SolverError):
        clayton_d_copula(3, 1.7).cdf([0.5, 0.5])  # dim mismatch
    with pytest.raises(SolverError):
        build_clayton_rosenblatt([Marginal("normal", 0.0, 1.0)], theta=1.7)  # too few marginals
