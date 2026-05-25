"""Wave HHHHHH (v14, D105): property tests for the v14 integration & production-wiring.

Randomised property checks complementing the per-wave anchor tests:
- balanced (+θ/−θ) laminates zero A₁₆=A₂₆ for arbitrary angle sets (D101);
- discrete angle selection (max_bending) dominates every random multiset (D102);
- the Gumbel series copula at θ=1 reduces to the independent series P_f (D098).
"""

from __future__ import annotations

from itertools import combinations_with_replacement
from math import erf, sqrt

import numpy as np
from structure_optimizer.core.orthotropic_simp import (
    is_balanced_laminate,
    laminate_abd,
    make_balanced_laminate,
    orthotropic_plane_stress_matrix,
    select_ply_angles,
)
from structure_optimizer.core.reliability import (
    ExchangeableGumbelCopula,
    system_reliability_series_copula,
)

_D0 = orthotropic_plane_stress_matrix(140e3, 10e3, 0.3, 5e3)


def _phi(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def test_property_balanced_laminate_zeros_extension_shear():
    """For arbitrary distinct off-axis angles, a balanced ±θ stack has A₁₆=A₂₆=0."""
    rng = np.random.default_rng(140)
    for _ in range(12):
        k = int(rng.integers(2, 5))
        angles = rng.uniform(np.radians(5.0), np.radians(85.0), size=k)  # off the 0/π2 axes
        stack = make_balanced_laminate(angles, symmetric=False)
        a, _, _ = laminate_abd(_D0, stack, np.full(len(stack), 0.125))
        assert abs(a[0, 2]) <= 1e-6
        assert abs(a[1, 2]) <= 1e-6
        assert is_balanced_laminate(stack) is True


def test_property_angle_selection_dominates_random_multisets():
    """max_bending angle selection's D_11 is ≥ every size-n candidate multiset's D_11."""
    rng = np.random.default_rng(141)
    t = 0.2
    for _ in range(8):
        cands = np.deg2rad(rng.choice([0.0, 30.0, 45.0, 60.0, 90.0], size=3, replace=False).astype(float))
        n = int(rng.integers(2, 5))
        best = select_ply_angles(_D0, cands, n, thickness=t, objective="max_bending").objective_value
        for combo in combinations_with_replacement(cands.tolist(), n):
            d11 = laminate_abd(_D0, np.array(combo), np.full(n, t))[2][0, 0]
            assert d11 <= best + 1e-6  # all-stiffest selection is the global maximum


def test_property_gumbel_series_copula_independence_reduction():
    """The Gumbel series copula at θ=1 reduces exactly to 1 − Π Φ(β_k) (independence)."""
    rng = np.random.default_rng(142)
    for _ in range(12):
        m = int(rng.integers(2, 5))
        betas = rng.uniform(1.0, 3.5, size=m)
        cop = ExchangeableGumbelCopula(m, 1.0)  # θ=1 ⟹ independence
        pf = system_reliability_series_copula(betas, cop)
        indep = 1.0 - float(np.prod([_phi(b) for b in betas]))
        assert abs(pf - indep) <= 1e-9
