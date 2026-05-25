"""Wave DDDDDD (v14, D101) — balanced laminate constraint (A₁₆=A₂₆=0).

Quantitative analytical anchors (exact coupling-term cancellation), never qualitative
trends. Traces D095's reopening criterion: "balanced-laminate constraint (+θ/−θ pairs
⟹ A₁₆=A₂₆=0) alongside the symmetric B=0 constraint".

Angles are in **radians** (the rotate_plane_stress / laminate_abd convention).
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.orthotropic_simp import (
    is_balanced_laminate,
    laminate_abd,
    make_balanced_laminate,
    orthotropic_plane_stress_matrix,
)

_D0 = orthotropic_plane_stress_matrix(e1=140e3, e2=10e3, nu12=0.3, g12=5e3)
_T = 0.125


def _coupling(angles):
    """Return (A₁₆, A₂₆, ‖B‖) for a uniform-thickness stack."""
    a, b, _ = laminate_abd(_D0, np.asarray(angles, dtype=float), np.full(len(angles), _T))
    return a[0, 2], a[1, 2], float(np.linalg.norm(b))


def test_balanced_zeros_extension_shear_coupling():
    """A balanced (+θ/−θ) stack has A₁₆ = A₂₆ = 0 exactly (odd Q̄₁₆/Q̄₂₆ cancel)."""
    stack = make_balanced_laminate(np.deg2rad([30.0, 60.0]), symmetric=False)
    a16, a26, _ = _coupling(stack)
    assert a16 == pytest.approx(0.0, abs=1e-7)
    assert a26 == pytest.approx(0.0, abs=1e-7)


def test_symmetric_balanced_zeros_both_couplings():
    """A symmetric-balanced stack zeros BOTH A₁₆=A₂₆ (balance) AND B (symmetry)."""
    stack = make_balanced_laminate(np.deg2rad([30.0, 60.0]), symmetric=True)
    a16, a26, bnorm = _coupling(stack)
    assert a16 == pytest.approx(0.0, abs=1e-7)
    assert a26 == pytest.approx(0.0, abs=1e-7)
    assert bnorm < 1e-7
    # the constructed stack is mirror-symmetric (full = half + reversed half)
    assert np.allclose(stack, stack[::-1])


def test_unbalanced_stack_has_nonzero_coupling():
    """The contrast: an unbalanced [+45,+45] stack has large A₁₆≠0 (and is_balanced False)."""
    a16, a26, _ = _coupling(np.deg2rad([45.0, 45.0]))
    assert abs(a16) > 1e3
    assert abs(a26) > 1e3
    assert is_balanced_laminate(np.deg2rad([45.0, 45.0])) is False


def test_is_balanced_detects_pairing_and_self_balanced():
    """is_balanced_laminate: True for ±θ pairs and for 0/π2 self-balanced plies."""
    assert is_balanced_laminate(np.deg2rad([45.0, -45.0])) is True
    assert is_balanced_laminate(np.deg2rad([30.0, -30.0, 60.0, -60.0])) is True
    assert is_balanced_laminate(np.deg2rad([0.0, 90.0])) is True  # both self-balanced
    assert is_balanced_laminate(np.deg2rad([0.0, 45.0])) is False  # lone +45


def test_balance_is_thickness_weighted():
    """Balance requires equal +θ/−θ *thickness*, not just equal counts."""
    assert is_balanced_laminate(np.deg2rad([45.0, -45.0]), [1.0, 1.0]) is True
    assert is_balanced_laminate(np.deg2rad([45.0, -45.0]), [2.0, 1.0]) is False
    # and the unequal-thickness stack indeed has nonzero A₁₆
    a, _, _ = laminate_abd(_D0, np.deg2rad([45.0, -45.0]), np.array([2.0, 1.0]))
    assert abs(a[0, 2]) > 1e3


def test_balanced_laminate_guards():
    """Empty-plies and thickness-count guards raise SolverError."""
    with pytest.raises(SolverError, match="balanced_laminate_no_plies"):
        is_balanced_laminate(np.array([]))
    with pytest.raises(SolverError, match="balanced_laminate_thickness_count_mismatch"):
        is_balanced_laminate(np.deg2rad([45.0, -45.0]), [1.0])
