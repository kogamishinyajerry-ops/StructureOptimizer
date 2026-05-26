"""Wave FFFFFFFF (v16, D119) — copula parallel / k-out-of-n system reliability (closes
D111's "parallel / general system events beyond series safety" reopening).

D098's system_reliability_series_copula modelled only the series system (1 − C(u)). This
adds the parallel system (fails iff ALL fail) and the unifying k-out-of-m system (fails iff
≥k fail), with k=1 ⟹ series and k=m ⟹ parallel as exact special cases. Quantitative
analytical anchors, never qualitative trends.
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    _standard_normal_cdf,
    gumbel_d_copula,
    system_reliability_k_out_of_n_copula,
    system_reliability_parallel_copula,
    system_reliability_series_copula,
)

_BETAS = np.array([2.0, 2.5, 3.0, 1.8])
_M = _BETAS.size
_U = np.array([_standard_normal_cdf(b) for b in _BETAS])


def test_independence_parallel_is_product_of_fail_probs():
    """Headline: with the independence copula the parallel system P_f = ∏_k (1 − Φ(β_k)) =
    ∏ P(fail) — independent modes all failing is the product (machine precision)."""
    pf = system_reliability_parallel_copula(_BETAS, gumbel_d_copula(_M, 1.0))
    assert pf == pytest.approx(float(np.prod(1.0 - _U)), abs=1e-14)


def test_k1_equals_series_pf():
    """k=1 (at least one fails) reduces exactly to the series P_f = 1 − C(u) for any
    copula (inclusion–exclusion for the union)."""
    cop = gumbel_d_copula(_M, 2.5)
    pf_k1 = system_reliability_k_out_of_n_copula(_BETAS, cop, 1)
    assert pf_k1 == pytest.approx(system_reliability_series_copula(_BETAS, cop), abs=1e-12)


def test_km_equals_parallel():
    """k=m (all fail) reduces exactly to the parallel P_f."""
    cop = gumbel_d_copula(_M, 2.5)
    pf_km = system_reliability_k_out_of_n_copula(_BETAS, cop, _M)
    assert pf_km == pytest.approx(system_reliability_parallel_copula(_BETAS, cop), abs=1e-12)


def test_parallel_le_series():
    """A parallel system is at least as reliable as the series system: P_f_parallel ≤
    P_f_series for any copula (fails only if all fail vs if any fails)."""
    cop = gumbel_d_copula(_M, 2.5)
    assert system_reliability_parallel_copula(_BETAS, cop) <= system_reliability_series_copula(_BETAS, cop)


def test_k_out_of_n_monotone_in_k():
    """P(≥k fail) is non-increasing in k (a stricter failure criterion is less likely), and
    every value is a valid probability in [0,1]."""
    cop = gumbel_d_copula(_M, 2.5)
    ks = [system_reliability_k_out_of_n_copula(_BETAS, cop, k) for k in range(1, _M + 1)]
    assert all(ks[i] >= ks[i + 1] for i in range(len(ks) - 1))
    assert all(0.0 <= x <= 1.0 for x in ks)


def test_parallel_copula_guards():
    """Guards: copula-dim mismatch, no modes, and k out of [1,m] raise SolverError."""
    cop = gumbel_d_copula(_M, 2.0)
    with pytest.raises(SolverError, match="system_reliability_copula_dim_mismatch"):
        system_reliability_parallel_copula(_BETAS, gumbel_d_copula(3, 2.0))
    with pytest.raises(SolverError, match="system_reliability_no_modes"):
        system_reliability_parallel_copula(np.array([]), gumbel_d_copula(2, 2.0))
    with pytest.raises(SolverError, match="system_reliability_k_out_of_range"):
        system_reliability_k_out_of_n_copula(_BETAS, cop, 0)
    with pytest.raises(SolverError, match="system_reliability_k_out_of_range"):
        system_reliability_k_out_of_n_copula(_BETAS, cop, _M + 1)
