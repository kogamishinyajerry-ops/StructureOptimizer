"""Wave AAAAAAA (v15, D106) — balanced constraint embedded in optimize_stacking_sequence.

Closes D101's reopening criterion ("wire balanced=True into optimize_stacking_sequence").
Quantitative analytical anchors proving the embedded constraint **truly binds** (the v15
discipline): (a) feasible — balanced=True ⟹ A₁₆=A₂₆=0; (b) changes the design —
balanced=False on the same input has A₁₆≠0; (c) opt-in default reproduces D095 byte-exact.

Angles are in **radians** (the rotate_plane_stress / laminate_abd convention).
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.orthotropic_simp import (
    _balanced_stacking_inventory,
    laminate_abd,
    make_balanced_laminate,
    optimize_stacking_sequence,
    orthotropic_plane_stress_matrix,
)

_D0 = orthotropic_plane_stress_matrix(e1=140e3, e2=10e3, nu12=0.3, g12=5e3)
_T = 0.125


def test_balanced_stacking_is_feasible_a16_a26_zero():
    """balanced=True ⟹ the optimiser output has A₁₆=A₂₆=0 (extension–shear decoupled)."""
    res = optimize_stacking_sequence(_D0, np.deg2rad([30.0, 60.0]), _T, objective="max_bending", balanced=True)
    assert res.a_matrix[0, 2] == pytest.approx(0.0, abs=1e-7)
    assert res.a_matrix[1, 2] == pytest.approx(0.0, abs=1e-7)
    # the inventory was replaced by its +θ/−θ paired multiset
    assert np.allclose(np.sort(res.sequence), np.sort(_balanced_stacking_inventory(np.deg2rad([30.0, 60.0]))))


def test_balanced_constraint_changes_the_design():
    """balanced=False on the same angles is NOT balanced (A₁₆≠0) — the constraint binds."""
    raw = optimize_stacking_sequence(_D0, np.deg2rad([30.0, 60.0]), _T, objective="max_bending", balanced=False)
    bal = optimize_stacking_sequence(_D0, np.deg2rad([30.0, 60.0]), _T, objective="max_bending", balanced=True)
    assert abs(raw.a_matrix[0, 2]) > 1e3  # unbalanced raw inventory
    assert abs(bal.a_matrix[0, 2]) < 1e-7  # balanced output
    assert bal.sequence.size != raw.sequence.size  # design genuinely differs (paired multiset)


def test_symmetric_balanced_zeros_both_a_and_b():
    """symmetric=True + balanced=True ⟹ A₁₆=A₂₆=0 (balance) AND ‖B‖=0 (symmetry)."""
    res = optimize_stacking_sequence(
        _D0, np.deg2rad([30.0, 60.0]), _T, objective="max_bending", symmetric=True, balanced=True
    )
    assert res.a_matrix[0, 2] == pytest.approx(0.0, abs=1e-7)
    assert res.a_matrix[1, 2] == pytest.approx(0.0, abs=1e-7)
    assert float(np.linalg.norm(res.b_matrix)) < 1e-7
    assert np.allclose(res.sequence, res.sequence[::-1])  # mirror-symmetric


def test_balanced_default_false_byte_exact_reproduces_d095():
    """v15 integration铁律: balanced=False (default) reproduces D095 byte-for-byte."""
    inv = np.deg2rad([0.0, 45.0, 90.0, -45.0])
    ref = optimize_stacking_sequence(_D0, inv, _T, objective="min_coupling")  # D095 default path
    same = optimize_stacking_sequence(_D0, inv, _T, objective="min_coupling", balanced=False)
    assert np.array_equal(ref.sequence, same.sequence)
    assert np.array_equal(ref.a_matrix, same.a_matrix)
    assert np.array_equal(ref.b_matrix, same.b_matrix)
    assert np.array_equal(ref.d_matrix, same.d_matrix)
    assert ref.objective_value == same.objective_value


def test_balance_survives_both_objectives_order_independent():
    """A-balance is order-independent: balanced=True holds under max_bending AND min_coupling."""
    for obj in ("max_bending", "min_coupling"):
        res = optimize_stacking_sequence(_D0, np.deg2rad([30.0, 60.0]), _T, objective=obj, balanced=True)
        assert abs(res.a_matrix[0, 2]) < 1e-7 and abs(res.a_matrix[1, 2]) < 1e-7
    # cross-check against an independent laminate_abd on the paired multiset
    paired = make_balanced_laminate(np.deg2rad([30.0, 60.0]), symmetric=False)
    a, _, _ = laminate_abd(_D0, paired, np.full(len(paired), _T))
    assert abs(a[0, 2]) < 1e-7


def test_balanced_min_coupling_too_many_plies_guard():
    """Pairing doubles the inventory; min_coupling's n≤8 brute-force guard still fires."""
    with pytest.raises(SolverError, match="stacking_min_coupling_too_many_plies"):
        optimize_stacking_sequence(
            _D0, np.deg2rad([10.0, 20.0, 30.0, 40.0, 50.0]), _T, objective="min_coupling", balanced=True
        )
