"""Wave HHHHHHH (v15, D113): property tests for the v15 embedded-constraints milestone.

Randomised property checks complementing the per-wave anchor tests:
- anti-symmetric stacks zero bending–shear D₁₆=D₂₆ for arbitrary angle sets (D110);
- the multi-family mixture series-P_f equals the convex combination of the component
  P_f's for arbitrary simplex weights and families (D111);
- the CBC generating vector's deterministic worst-case error never exceeds the textbook
  Korobov vector's, for arbitrary product weights (D112).
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.core.orthotropic_simp import (
    laminate_abd,
    make_antisymmetric_laminate,
    orthotropic_plane_stress_matrix,
)
from structure_optimizer.core.reliability import (
    _korobov_generating_vector,
    cbc_korobov_generating_vector,
    clayton_d_copula,
    gumbel_d_copula,
    korobov_worst_case_error,
    multi_family_copula,
    system_reliability_series_copula,
)

_D0 = orthotropic_plane_stress_matrix(140e3, 10e3, 0.3, 5e3)


def test_property_antisymmetric_zeros_bending_shear():
    """For arbitrary distinct off-axis angles, an anti-symmetric stack has D₁₆=D₂₆=0
    (the bending–shear decoupling identity, D110), to machine precision."""
    rng = np.random.default_rng(150)
    for _ in range(12):
        k = int(rng.integers(2, 5))
        half = rng.uniform(np.radians(5.0), np.radians(85.0), size=k)  # off the 0/π2 axes
        stack = make_antisymmetric_laminate(half)
        _, _, d = laminate_abd(_D0, stack, np.full(len(stack), 0.125))
        assert abs(d[0, 2]) < 1e-6
        assert abs(d[1, 2]) < 1e-6


def test_property_mixture_pf_is_convex_combination():
    """For arbitrary simplex weights over Gumbel+Clayton families, the mixture series-P_f
    equals Σ w_k P_f(C_k) (the exact convex-combination identity, D111)."""
    rng = np.random.default_rng(151)
    m = 4
    betas = np.array([2.0, 2.5, 3.0, 1.8])
    for _ in range(12):
        comps = [gumbel_d_copula(m, 1.0 + 5.0 * rng.random()), clayton_d_copula(m, 0.1 + 4.0 * rng.random())]
        w = rng.random(2)
        w = w / w.sum()
        pf_each = np.array([system_reliability_series_copula(betas, c) for c in comps])
        pf_mix = system_reliability_series_copula(betas, multi_family_copula(comps, w))
        assert pf_mix == np.float64(pf_mix)  # finite
        np.testing.assert_allclose(pf_mix, float(w @ pf_each), atol=1e-13)


def test_property_cbc_never_worse_than_korobov():
    """For arbitrary product weights, the CBC vector's deterministic worst-case error is
    ≤ the textbook Korobov vector's for the same N (greedy optimality, D112)."""
    rng = np.random.default_rng(152)
    n = 61  # prime
    for _ in range(8):
        d = int(rng.integers(2, 5))
        gamma = rng.uniform(0.05, 1.0, size=d)
        e_cbc = korobov_worst_case_error(cbc_korobov_generating_vector(d, n, gamma), n, gamma)
        e_kor = korobov_worst_case_error(_korobov_generating_vector(d, 17, n), n, gamma)
        assert e_cbc <= e_kor + 1e-15
        assert e_cbc >= -1e-12  # a genuine (non-negative) error
