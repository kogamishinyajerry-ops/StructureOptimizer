"""Wave FFFFFFF (v15, D111) — multi-family mixture copula in series-system reliability.

Closes D098's reopening ("other families / general dependence beyond a single
exchangeable Archimedean copula"). Quantitative analytical anchors (the exact
convex-combination P_f identity + bit-exact single-component reproduction), never
qualitative trends.

INTEGRATION DISCIPLINE (v15 "constraint truly binds" + byte-exact opt-in default):
(a) the mixture P_f is FEASIBLE (a valid probability from a valid copula — uniform
margins); (b) a 0<w<1 mixture CHANGES the answer vs either pure family (it lies strictly
between them — neither Gumbel nor Clayton alone represents a mixed-tail system); (c) a
single-component mixture reproduces the pure-family `system_reliability_series_copula`
BIT-EXACTLY (the backward-compatible opt-in default — the mixture subsumes D098).
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    clayton_d_copula,
    gumbel_d_copula,
    multi_family_copula,
    system_reliability_series_copula,
)

_BETAS = np.array([2.0, 2.5, 3.0, 1.8])
_M = _BETAS.size


def test_mixture_pf_is_convex_combination_of_components():
    """Headline: P_f(mixture) = Σ w_k P_f(C_k) exactly (since P_f = 1 − C and Σ w_k = 1).

    A Gumbel (upper-tail) + Clayton (lower-tail) blend's series failure probability is
    the weight-average of the two pure-family failure probabilities, to machine precision.
    """
    gum = gumbel_d_copula(_M, 3.0)
    cla = clayton_d_copula(_M, 2.0)
    w = 0.65
    pf_gum = system_reliability_series_copula(_BETAS, gum)
    pf_cla = system_reliability_series_copula(_BETAS, cla)
    pf_mix = system_reliability_series_copula(_BETAS, multi_family_copula([gum, cla], [w, 1.0 - w]))
    assert pf_mix == pytest.approx(w * pf_gum + (1.0 - w) * pf_cla, abs=1e-14)


def test_single_component_mixture_is_bit_exact_pure_family():
    """Backward-compat / opt-in default: a one-component mixture (w=1) reproduces the pure
    `system_reliability_series_copula` path bit-exactly — the mixture subsumes D098."""
    gum = gumbel_d_copula(_M, 3.0)
    pf_pure = system_reliability_series_copula(_BETAS, gum)
    pf_mix = system_reliability_series_copula(_BETAS, multi_family_copula([gum], [1.0]))
    assert pf_mix == pf_pure  # exact equality, not approx
    # a two-component mixture with a zero weight is likewise exactly the surviving family
    cla = clayton_d_copula(_M, 2.0)
    pf_mix0 = system_reliability_series_copula(_BETAS, multi_family_copula([gum, cla], [1.0, 0.0]))
    assert pf_mix0 == pf_pure


def test_mixture_changes_the_answer_strictly_between_families():
    """Binding evidence: with 0<w<1 the mixture P_f is strictly between (and ≠) each pure
    family's P_f — neither Gumbel nor Clayton alone gives the mixed-tail answer."""
    gum = gumbel_d_copula(_M, 8.0)  # strong upper-tail → low P_f
    cla = clayton_d_copula(_M, 0.5)  # weak lower-tail → P_f nearer independence
    pf_gum = system_reliability_series_copula(_BETAS, gum)
    pf_cla = system_reliability_series_copula(_BETAS, cla)
    assert pf_gum != pytest.approx(pf_cla, abs=1e-6)  # the two families genuinely differ
    lo, hi = sorted((pf_gum, pf_cla))
    pf_mix = system_reliability_series_copula(_BETAS, multi_family_copula([gum, cla], [0.5, 0.5]))
    assert lo < pf_mix < hi


def test_mixture_has_uniform_margins_valid_copula():
    """The mixture is a valid copula: setting all but one argument to 1 returns that
    argument exactly, C(1,…,u_i,…,1)=u_i (the Sklar margin property survives the convex
    combination)."""
    mix = multi_family_copula([gumbel_d_copula(_M, 4.0), clayton_d_copula(_M, 3.0)], [0.4, 0.6])
    for i in range(_M):
        u = np.ones(_M)
        u[i] = 0.37
        assert mix.cdf(u) == pytest.approx(0.37, abs=1e-12)


def test_three_family_partition_of_unity():
    """Generalises to ≥3 components: the convex-combination identity holds for a
    three-family mixture (Gumbel + two Claytons) with weights on the simplex."""
    cs = [gumbel_d_copula(_M, 5.0), clayton_d_copula(_M, 1.0), clayton_d_copula(_M, 4.0)]
    ws = np.array([0.2, 0.5, 0.3])
    pf_each = np.array([system_reliability_series_copula(_BETAS, c) for c in cs])
    pf_mix = system_reliability_series_copula(_BETAS, multi_family_copula(cs, ws))
    assert pf_mix == pytest.approx(float(ws @ pf_each), abs=1e-14)


def test_multi_family_copula_guards():
    """Guards: weight/component count mismatch, negative weight, un-normalised weights,
    mismatched component dims, and empty components all raise SolverError."""
    gum = gumbel_d_copula(_M, 2.0)
    cla = clayton_d_copula(_M, 2.0)
    with pytest.raises(SolverError, match="mixture_copula_weight_count_mismatch"):
        multi_family_copula([gum, cla], [1.0])
    with pytest.raises(SolverError, match="mixture_copula_negative_weight"):
        multi_family_copula([gum, cla], [1.5, -0.5])
    with pytest.raises(SolverError, match="mixture_copula_weights_not_normalised"):
        multi_family_copula([gum, cla], [0.3, 0.3])
    with pytest.raises(SolverError, match="mixture_copula_component_dim_mismatch"):
        multi_family_copula([gum, clayton_d_copula(3, 2.0)], [0.5, 0.5])
    with pytest.raises(SolverError, match="mixture_copula_no_components"):
        multi_family_copula([], [])
