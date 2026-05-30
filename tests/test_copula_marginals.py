"""Wave BBBBBBBB (v16, D115) — mixture-copula system reliability with general non-normal
marginals (closes D111's reopening "general non-normal marginals").

D098/D111 fixed each mode's safe-probability to the standard-normal tail u_k = Φ(β_k).
This generalises it to any Marginal (Weibull/Gumbel/lognormal): u_k = F_k(x_k), coupled by
the copula. Quantitative analytical anchors, never qualitative trends.

v16 exact-generalization discipline: (a) the normal-marginal degenerate case reproduces
system_reliability_series_copula BIT-EXACTLY; (b) non-normal marginals give the true tail
CDF (vs closed form) — a quantity the normal-only path cannot represent.
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    Marginal,
    gumbel_d_copula,
    system_reliability_series_copula,
    system_reliability_series_copula_marginals,
)

_BETAS = np.array([2.0, 2.5, 3.0, 1.8])
_M = _BETAS.size


def test_normal_marginals_bit_exact_reduces_to_d098():
    """Backward-compat anchor: all-N(0,1) marginals + points=β reduce bit-exactly to
    system_reliability_series_copula (Marginal('normal',0,1).to_standard_normal(β)=β)."""
    cop = gumbel_d_copula(_M, 2.5)
    norm = [Marginal("normal", 0.0, 1.0)] * _M
    pf_orig = system_reliability_series_copula(_BETAS, cop)
    pf_gen = system_reliability_series_copula_marginals(norm, _BETAS, cop)
    assert pf_gen == pf_orig  # exact equality, not approx


def test_general_marginal_independence_matches_closed_form():
    """Generalization correctness: with the independence copula (Gumbel θ=1) the series P_f
    equals 1 − ∏ F_k(x_k) for the true Weibull / Gumbel CDFs (machine precision)."""
    indep = gumbel_d_copula(2, 1.0)
    mg = [Marginal("weibull", 2.0, 3.0), Marginal("gumbel", 1.0, 0.5)]
    pts = [2.5, 1.2]
    f0 = 1.0 - np.exp(-((pts[0] / 3.0) ** 2.0))  # Weibull CDF
    f1 = np.exp(-np.exp(-(pts[1] - 1.0) / 0.5))  # Gumbel CDF
    pf = system_reliability_series_copula_marginals(mg, pts, indep)
    assert pf == pytest.approx(1.0 - f0 * f1, abs=1e-10)


def test_non_normal_marginal_changes_pf():
    """A Weibull-strength mode gives a different P_f than a normal mode at the same physical
    point — the marginal tail genuinely matters (the new quantity the normal path misses)."""
    indep = gumbel_d_copula(2, 1.0)
    pf_w = system_reliability_series_copula_marginals(
        [Marginal("weibull", 2.0, 3.0), Marginal("normal", 0.0, 1.0)], [2.5, 1.2], indep
    )
    pf_n = system_reliability_series_copula_marginals(
        [Marginal("normal", 0.0, 1.0), Marginal("normal", 0.0, 1.0)], [2.5, 1.2], indep
    )
    assert abs(pf_w - pf_n) > 1e-3


def test_positive_dependence_lowers_pf_with_general_marginals():
    """The copula still binds with non-normal marginals: upper-tail (Gumbel θ>1) dependence
    lowers the series P_f vs the independence copula at the same marginals."""
    mg = [Marginal("weibull", 2.0, 3.0), Marginal("gumbel", 1.0, 0.5), Marginal("lognormal", 0.0, 0.3)]
    pts = [2.5, 1.2, 1.0]
    pf_indep = system_reliability_series_copula_marginals(mg, pts, gumbel_d_copula(3, 1.0))
    pf_dep = system_reliability_series_copula_marginals(mg, pts, gumbel_d_copula(3, 3.0))
    assert pf_dep < pf_indep


def test_more_margin_lowers_pf_monotonically():
    """Quantitative monotonicity: increasing every evaluation point (more safety margin)
    raises each u_k = F_k(x_k) and strictly lowers the series P_f."""
    indep = gumbel_d_copula(2, 1.0)
    mg = [Marginal("weibull", 2.0, 3.0), Marginal("gumbel", 1.0, 0.5)]
    pf_lo = system_reliability_series_copula_marginals(mg, [2.5, 1.2], indep)
    pf_hi = system_reliability_series_copula_marginals(mg, [4.0, 2.0], indep)
    assert pf_hi < pf_lo


def test_copula_marginals_guards():
    """Guards: point/marginal count mismatch, copula-dim mismatch, no modes."""
    cop = gumbel_d_copula(2, 2.0)
    norm2 = [Marginal("normal", 0.0, 1.0), Marginal("normal", 0.0, 1.0)]
    with pytest.raises(SolverError, match="system_reliability_marginals_point_mismatch"):
        system_reliability_series_copula_marginals(norm2, [1.0], cop)
    with pytest.raises(SolverError, match="system_reliability_copula_dim_mismatch"):
        system_reliability_series_copula_marginals(norm2, [1.0, 2.0], gumbel_d_copula(3, 2.0))
    with pytest.raises(SolverError, match="system_reliability_no_modes"):
        system_reliability_series_copula_marginals([], [], cop)
