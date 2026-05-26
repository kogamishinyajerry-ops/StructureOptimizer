"""Wave EEEEEEE (v15, D110) — anti-symmetric laminate bending-shear decoupling D₁₆=D₂₆=0.

Closes D101's reopening ("D₁₆/D₂₆ bending-shear decoupling (anti-symmetric stacks)").
Quantitative analytical anchors (exact coupling-term cancellation), never qualitative
trends. The headline: an anti-symmetric stack (θ(−z)=−θ(+z)) zeros D₁₆/D₂₆ — which a
symmetric-balanced stack (D101) cannot.

Angles are in **radians**.
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.orthotropic_simp import (
    is_antisymmetric_laminate,
    laminate_abd,
    make_antisymmetric_laminate,
    make_balanced_laminate,
    orthotropic_plane_stress_matrix,
)

_D0 = orthotropic_plane_stress_matrix(e1=140e3, e2=10e3, nu12=0.3, g12=5e3)
_T = 0.125


def _abd(stack):
    return laminate_abd(_D0, np.asarray(stack, dtype=float), np.full(len(stack), _T))


def test_antisymmetric_zeros_bending_shear_coupling():
    """The headline: an anti-symmetric stack has D₁₆=D₂₆=0 exactly (mirror plies share the
    z³ weight but carry ±θ whose odd Q̄₁₆/Q̄₂₆ cancel)."""
    stack = make_antisymmetric_laminate(np.deg2rad([30.0, 60.0]))
    _, _, d = _abd(stack)
    assert d[0, 2] == pytest.approx(0.0, abs=1e-7)
    assert d[1, 2] == pytest.approx(0.0, abs=1e-7)


def test_antisymmetric_is_also_balanced():
    """Anti-symmetry also zeros the extensional shear coupling A₁₆=A₂₆ (order-independent)."""
    a, _, _ = _abd(make_antisymmetric_laminate(np.deg2rad([15.0, 45.0, 75.0])))
    assert a[0, 2] == pytest.approx(0.0, abs=1e-7)
    assert a[1, 2] == pytest.approx(0.0, abs=1e-7)


def test_symmetric_balanced_does_not_decouple_bending_shear():
    """The contrast that makes anti-symmetry necessary: a symmetric-balanced stack (D101)
    keeps D₁₆,D₂₆ ≠ 0 — symmetry+balance alone cannot decouple bending–shear."""
    sym = make_balanced_laminate(np.deg2rad([30.0, 60.0]), symmetric=True)
    _, _, d = _abd(sym)
    assert abs(d[0, 2]) > 1e2
    assert abs(d[1, 2]) > 1e2


def test_antisymmetric_coupling_signature():
    """Anti-symmetry zeros the even-term B (B₁₁=B₁₂=B₂₂=0) but keeps B₁₆,B₂₆ ≠ 0 — it
    trades extension–bending B-coupling for bending–shear D-decoupling."""
    _, b, _ = _abd(make_antisymmetric_laminate(np.deg2rad([30.0, 60.0])))
    assert abs(b[0, 0]) < 1e-7 and abs(b[1, 1]) < 1e-7 and abs(b[0, 1]) < 1e-7
    assert abs(b[0, 2]) > 1e2  # B₁₆ ≠ 0


def test_is_antisymmetric_detection():
    """is_antisymmetric_laminate: True for a constructed anti-symmetric stack, False for
    a symmetric-balanced stack and for odd ply counts."""
    assert is_antisymmetric_laminate(make_antisymmetric_laminate(np.deg2rad([30.0, 60.0]))) is True
    assert is_antisymmetric_laminate(np.deg2rad([30.0, -30.0])) is True  # θ ≡ −(−θ)
    assert is_antisymmetric_laminate(make_balanced_laminate(np.deg2rad([30.0, 60.0]), symmetric=True)) is False
    assert is_antisymmetric_laminate(np.deg2rad([30.0, 60.0, -30.0])) is False  # odd count


def test_antisymmetric_guards():
    """Empty-plies guards raise SolverError."""
    with pytest.raises(SolverError, match="antisymmetric_no_plies"):
        make_antisymmetric_laminate(np.array([]))
    with pytest.raises(SolverError, match="antisymmetric_no_plies"):
        is_antisymmetric_laminate(np.array([]))
