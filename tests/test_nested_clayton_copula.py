"""Wave DDDD (v12, D085): nested/hierarchical Clayton copula with per-cluster θ.

Quantitative anchors (closed form, not qualitative trend):
- **degeneration**: all θ equal ⟹ the nested copula CDF equals
  :class:`ExchangeableClaytonCopula` (D077) exactly;
- **bivariate-margin structure** (the per-cluster + hierarchy payoff): the margin of
  two same-group variables equals Clayton(θ_g); of two different-group variables,
  Clayton(θ₀) — matched to the bivariate :class:`ArchimedeanCopula` in closed form;
- **per-cluster Kendall's τ**: within group g = θ_g/(θ_g+2) (differs across groups),
  between groups = θ₀/(θ₀+2) < every within-τ (nesting condition);
- **valid copula**: grounded (a zero argument ⟹ C=0), C(1,…,1)=1, density ≥ 0 on a
  grid; nesting-condition + partition guards.

D077's reopening criterion: "nested / hierarchical & non-Clayton d-dim copulas".
"""

from __future__ import annotations

from itertools import product

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    ArchimedeanCopula,
    ExchangeableClaytonCopula,
    nested_clayton_copula,
)

CLUSTERS = [[0, 1], [2, 3]]
TH_OUTER = 2.0
TH_INNER = [6.0, 4.0]


def _cop():
    return nested_clayton_copula(4, CLUSTERS, TH_OUTER, TH_INNER)


def test_degenerates_to_exchangeable_when_all_theta_equal():
    th = 3.0
    nested = nested_clayton_copula(4, CLUSTERS, th, [th, th])
    exch = ExchangeableClaytonCopula(4, th)
    rng = np.random.default_rng(0)
    for _ in range(20):
        u = rng.uniform(0.05, 0.95, size=4)
        assert abs(nested.cdf(u) - exch.cdf(u)) <= 1e-12


def test_bivariate_margins_match_inner_and_outer_clayton():
    c = _cop()
    c6 = ArchimedeanCopula(family="clayton", theta=6.0)
    c4 = ArchimedeanCopula(family="clayton", theta=4.0)
    c2 = ArchimedeanCopula(family="clayton", theta=2.0)
    for ui, uj in [(0.4, 0.6), (0.2, 0.9), (0.55, 0.55)]:
        assert abs(c.bivariate_margin_cdf(0, 1, ui, uj) - c6.cdf(ui, uj)) <= 1e-12  # same group 0
        assert abs(c.bivariate_margin_cdf(2, 3, ui, uj) - c4.cdf(ui, uj)) <= 1e-12  # same group 1
        assert abs(c.bivariate_margin_cdf(0, 2, ui, uj) - c2.cdf(ui, uj)) <= 1e-12  # cross-group
        assert abs(c.bivariate_margin_cdf(1, 3, ui, uj) - c2.cdf(ui, uj)) <= 1e-12  # cross-group


def test_per_cluster_kendall_tau():
    c = _cop()
    tau_g0 = c.kendall_tau_within(0)
    tau_g1 = c.kendall_tau_within(1)
    tau_between = c.kendall_tau_between()
    assert abs(tau_g0 - 6.0 / 8.0) <= 1e-12
    assert abs(tau_g1 - 4.0 / 6.0) <= 1e-12
    assert abs(tau_between - 2.0 / 4.0) <= 1e-12
    # within-cluster strictly stronger than between-cluster, and clusters differ
    assert tau_g0 > tau_g1 > tau_between


def test_copula_groundedness_and_uniform_margins():
    c = _cop()
    # C(1,...,1) = 1
    assert abs(c.cdf(np.ones(4)) - 1.0) <= 1e-12
    # a zero argument grounds the copula to 0 (limit)
    u = np.array([1e-9, 0.5, 0.5, 0.5])
    assert c.cdf(u) <= 1e-6
    # uniform margin: C(u_i, 1,1,1) = u_i
    for i in range(4):
        u = np.ones(4)
        u[i] = 0.37
        assert abs(c.cdf(u) - 0.37) <= 1e-9


def test_density_nonnegative_on_grid():
    """4th mixed partial (the copula density) ≥ 0 on a grid — a valid copula under
    the enforced nesting condition θ_g ≥ θ₀."""
    c = _cop()
    h = 1e-3
    pts = [np.array([a, b, cc, d]) for a in (0.3, 0.6) for b in (0.4, 0.7) for cc in (0.35, 0.65) for d in (0.45, 0.55)]
    for p in pts:
        s = 0.0
        for sgn in product([1, -1], repeat=4):
            uu = np.array([p[k] + sgn[k] * h for k in range(4)])
            s += float(np.prod(sgn)) * c.cdf(uu)
        density = s / ((2 * h) ** 4)
        assert density >= -1e-5, f"negative copula density {density:.3e} at {p}"


def test_guards():
    with pytest.raises(SolverError, match="nesting_condition_violated"):
        nested_clayton_copula(4, CLUSTERS, 3.0, [1.0, 4.0])  # inner 1.0 < outer 3.0
    with pytest.raises(SolverError, match="clusters_not_a_partition"):
        nested_clayton_copula(4, [[0, 1], [1, 2]], 2.0, [4.0, 4.0])  # 1 repeated, 3 missing
    with pytest.raises(SolverError, match="cluster_theta_count_mismatch"):
        nested_clayton_copula(4, CLUSTERS, 2.0, [4.0])
    with pytest.raises(SolverError, match="nonpositive_outer_theta"):
        nested_clayton_copula(4, CLUSTERS, 0.0, [4.0, 4.0])
