"""Wave CCCC (v12, D084): augmented-Tchebycheff R2 + Schott spacing indicator.

Quantitative anchors (closed form, not qualitative trend):
- **ρ=0 recovers plain R2 exactly** (augmented degenerates to :func:`r2_indicator`);
- **augmented ≥ plain** for ρ>0 (pointwise g_aug ≥ g_plain ⟹ the indicator too);
- **weak-vs-proper discrimination**: a front whose point is only *weakly* efficient
  under a weight scores identically to the properly-efficient (dominating) point in
  plain R2, but augmented R2 strictly prefers the dominating one — the defect the
  augmentation exists to fix;
- **spacing S = 0 for an evenly-spaced front**, S > 0 for a clustered one, and
  permutation-invariant.

D076's reopening criterion: "augmented Tchebycheff R2 + diversity indicator".
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.multi_objective_to import (
    augmented_tchebycheff_r2,
    r2_indicator,
    spacing_indicator,
)


def test_rho_zero_recovers_plain_r2():
    rng = np.random.default_rng(0)
    front = np.abs(rng.standard_normal((6, 2)))
    w = np.array([[0.2, 0.8], [0.5, 0.5], [0.9, 0.1]])
    z = np.zeros(2)
    plain = r2_indicator(front, weights=w, ideal=z)
    aug0 = augmented_tchebycheff_r2(front, weights=w, ideal=z, rho=0.0)
    assert abs(aug0 - plain) <= 1e-12, f"ρ=0 augmented {aug0} != plain {plain}"


def test_augmented_geq_plain_for_positive_rho():
    rng = np.random.default_rng(1)
    front = np.abs(rng.standard_normal((8, 3))) + 0.1
    z = np.zeros(3)  # front strictly above utopia ⟹ ℓ₁ term ≥ 0
    plain = r2_indicator(front, ideal=z)
    aug = augmented_tchebycheff_r2(front, ideal=z, rho=0.05)
    assert aug >= plain - 1e-12, f"augmented {aug} < plain {plain}"


def test_weak_vs_proper_discrimination():
    """Under λ=(0.5,0.5), z*=0: the weakly-efficient (0.5,0.5) and the properly-
    efficient (0.5,0.3) (which dominates it) have IDENTICAL plain-Tchebycheff
    utility (the max binds on the first coord, 0.25). Augmented R2 strictly prefers
    the dominating point."""
    w = np.array([[0.5, 0.5]])
    z = np.zeros(2)
    weak = np.array([[0.5, 0.5]])
    proper = np.array([[0.5, 0.3]])  # dominates weak (equal f1, smaller f2)
    # plain R2 is indifferent
    assert abs(r2_indicator(weak, weights=w, ideal=z) - r2_indicator(proper, weights=w, ideal=z)) <= 1e-12
    # augmented R2 strictly prefers the dominating front (lower is better)
    a_weak = augmented_tchebycheff_r2(weak, weights=w, ideal=z, rho=0.1)
    a_proper = augmented_tchebycheff_r2(proper, weights=w, ideal=z, rho=0.1)
    assert a_proper < a_weak, f"augmented did not discriminate: proper {a_proper} !< weak {a_weak}"
    # exact closed-form values: 0.25 + 0.1·(0.25+0.25)=0.30 ; 0.25 + 0.1·(0.25+0.15)=0.29
    assert abs(a_weak - 0.30) <= 1e-12 and abs(a_proper - 0.29) <= 1e-12


def test_spacing_zero_for_evenly_spaced_front():
    even = np.array([[0.0, 3.0], [1.0, 2.0], [2.0, 1.0], [3.0, 0.0]])  # ℓ₁ nn = 2 everywhere
    assert spacing_indicator(even) <= 1e-12


def test_spacing_positive_for_clustered_front_and_permutation_invariant():
    clustered = np.array([[0.0, 3.0], [0.1, 2.9], [2.0, 1.0], [3.0, 0.0]])
    s = spacing_indicator(clustered)
    assert s > 1e-6, "clustered front should have positive spacing std"
    # permutation invariance
    rng = np.random.default_rng(3)
    perm = rng.permutation(clustered.shape[0])
    assert abs(spacing_indicator(clustered[perm]) - s) <= 1e-12
    # an even front is strictly more uniform (smaller S) than the clustered one
    even = np.array([[0.0, 3.0], [1.0, 2.0], [2.0, 1.0], [3.0, 0.0]])
    assert spacing_indicator(even) < s


def test_guards():
    with pytest.raises(SolverError, match="augmented_r2_negative_rho"):
        augmented_tchebycheff_r2(np.array([[1.0, 1.0]]), rho=-0.1)
    with pytest.raises(SolverError, match="augmented_r2_empty_front"):
        augmented_tchebycheff_r2(np.empty((0, 2)))
    with pytest.raises(SolverError, match="spacing_needs_two_points"):
        spacing_indicator(np.array([[1.0, 2.0]]))
    with pytest.raises(SolverError, match="spacing_expects_2d_front"):
        spacing_indicator(np.array([1.0, 2.0, 3.0]))
