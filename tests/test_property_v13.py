"""Wave HHHHH (v13, D097): property tests for the v13 robust drivers & validated geometry.

Randomised property checks complementing the per-wave anchor tests:
- d-Gumbel copula at d=2 degenerates to the bivariate Gumbel conditional CDF (D093);
- range-adaptive aug-R2 is scale-invariant and extent scales linearly (D092);
- stacking max_bending (rearrangement) dominates every random permutation (D095).
"""

from __future__ import annotations

from itertools import permutations

import numpy as np
from structure_optimizer.core.multi_objective_to import augmented_tchebycheff_r2, extent_indicator
from structure_optimizer.core.orthotropic_simp import (
    laminate_abd,
    optimize_stacking_sequence,
    orthotropic_plane_stress_matrix,
)
from structure_optimizer.core.reliability import gumbel_copula, gumbel_d_copula


def test_property_gumbel_d2_degenerates_to_bivariate():
    rng = np.random.default_rng(21)
    for _ in range(10):
        theta = float(rng.uniform(1.0, 6.0))
        g2 = gumbel_d_copula(2, theta)
        biv = gumbel_copula(theta)
        u1, u2 = rng.uniform(0.05, 0.95, size=2)
        assert abs(g2.cdf([u1, u2]) - biv.cdf(u1, u2)) <= 1e-10
        assert abs(g2.conditional_cdf([u1, u2]) - biv.conditional_cdf(u1, u2)) <= 1e-10
        assert abs(g2.kendall_tau() - (1.0 - 1.0 / theta)) <= 1e-12


def test_property_range_adaptive_scale_invariant_and_extent_linear():
    rng = np.random.default_rng(22)
    w = np.array([[1.0, 0.0], [0.5, 0.5], [0.0, 1.0]])
    for _ in range(10):
        front = rng.uniform(0.0, 10.0, size=(6, 2))
        scale = float(rng.uniform(10.0, 1000.0))
        scaled = front.copy()
        scaled[:, 0] *= scale
        base = augmented_tchebycheff_r2(front, weights=w, rho=0.05, normalize_ranges=True)
        sc = augmented_tchebycheff_r2(scaled, weights=w, rho=0.05, normalize_ranges=True)
        assert abs(sc - base) <= 1e-9 * max(1.0, abs(base))  # scale-invariant
        # extent is translation-invariant
        shifted = front + rng.uniform(-5.0, 5.0)
        assert abs(extent_indicator(shifted) - extent_indicator(front)) <= 1e-9 * extent_indicator(front)


def test_property_stacking_max_bending_dominates_all_permutations():
    rng = np.random.default_rng(23)
    d0 = orthotropic_plane_stress_matrix(140e3, 10e3, 0.3, 5e3)
    t = 0.2
    for _ in range(8):
        inv = rng.choice([0.0, 45.0, -45.0, 90.0], size=5).astype(float)
        res = optimize_stacking_sequence(d0, inv, t, objective="max_bending")
        best = res.objective_value
        for perm in {tuple(p) for p in permutations(inv.tolist())}:
            d11 = laminate_abd(d0, np.array(perm), np.full(len(perm), t))[2][0, 0]
            assert d11 <= best + 1e-6  # rearrangement is the global maximum
