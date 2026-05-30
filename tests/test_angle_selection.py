"""Wave EEEEEE (v14, D102) — discrete angle-set *selection* (beyond ordering).

Quantitative analytical anchors (closed-form D_11, exact ‖B‖=0 floor, exhaustive
provably-global confirmation), never qualitative trends. Traces D095's reopening
criterion: "angle-value selection beyond ordering".

v14 integration铁律: select_ply_angles delegates the final arrangement to the existing
production ordering optimiser optimize_stacking_sequence (D095); the bit-exact reuse
anchor proves that composition does not alter D095's behaviour.

Angles are in **radians** (the rotate_plane_stress / laminate_abd convention).
"""

from itertools import product

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.orthotropic_simp import (
    laminate_abd,
    optimize_stacking_sequence,
    orthotropic_plane_stress_matrix,
    rotate_plane_stress,
    select_ply_angles,
)

_D0 = orthotropic_plane_stress_matrix(e1=140e3, e2=10e3, nu12=0.3, g12=5e3)
_T = 0.125
_CANDS = np.deg2rad([0.0, 45.0, 90.0])  # {0, π/4, π/2}


def test_max_bending_closed_form_all_best_angle():
    """max_bending selects n copies of θ*=argmax Q̄_11; D_11=(h³/12)·Q̄_11(θ*) closed form."""
    n = 4
    res = select_ply_angles(_D0, _CANDS, n, thickness=_T, objective="max_bending")
    q11 = np.array([rotate_plane_stress(_D0, float(a))[0, 0] for a in _CANDS])
    theta_star = float(_CANDS[int(np.argmax(q11))])
    assert np.allclose(res.sequence, theta_star)  # all plies at the stiffest angle (=0)
    h = n * _T
    expected_d11 = (h**3 / 12.0) * q11.max()
    assert res.d_matrix[0, 0] == pytest.approx(expected_d11, rel=1e-9)


def test_max_bending_provably_global_vs_exhaustive():
    """Exhaustive over ALL |C|^n angle assignments confirms the closed form is global."""
    n = 3
    res = select_ply_angles(_D0, _CANDS, n, thickness=_T, objective="max_bending")
    best_brute = -np.inf
    for assignment in product(_CANDS.tolist(), repeat=n):
        _, _, d = laminate_abd(_D0, np.array(assignment), np.full(n, _T))
        best_brute = max(best_brute, d[0, 0])
    assert res.d_matrix[0, 0] == pytest.approx(best_brute, rel=1e-9)


def test_selection_beats_mixed_inventory():
    """Selecting all-stiffest strictly beats ORDERING a fixed mixed inventory (D095)."""
    n = 4
    sel = select_ply_angles(_D0, _CANDS, n, thickness=_T, objective="max_bending")
    mixed = optimize_stacking_sequence(_D0, np.deg2rad([0.0, 45.0, 90.0, 45.0]), thickness=_T, objective="max_bending")
    assert sel.d_matrix[0, 0] > mixed.d_matrix[0, 0] + 1.0  # strictly stiffer


def test_min_coupling_reaches_zero_floor():
    """min_coupling brute-forces multisets; a balanced {±π/4} pick hits ‖B‖=0 exactly."""
    cands = np.deg2rad([-45.0, 45.0])
    res = select_ply_angles(_D0, cands, 4, thickness=_T, objective="min_coupling")
    assert res.objective_value < 1e-7  # symmetric balanced ordering ⟹ B=0
    assert float(np.linalg.norm(res.b_matrix)) < 1e-7


def test_integration_bit_exact_reuse_of_d095():
    """Single-candidate selection bit-exactly reproduces optimize_stacking_sequence (D095).

    The v14 integration anchor: D102 composes with D095 without altering it.
    """
    theta = np.array([0.3])  # one candidate ⟹ the only multiset is [0.3]*n
    n = 4
    sel = select_ply_angles(_D0, theta, n, thickness=_T, objective="max_bending")
    ref = optimize_stacking_sequence(_D0, np.full(n, 0.3), thickness=_T, objective="max_bending")
    assert np.array_equal(sel.sequence, ref.sequence)
    assert np.array_equal(sel.a_matrix, ref.a_matrix)
    assert np.array_equal(sel.b_matrix, ref.b_matrix)
    assert np.array_equal(sel.d_matrix, ref.d_matrix)
    assert sel.objective_value == ref.objective_value


def test_select_ply_angles_guards():
    """Empty candidates / nonpositive plies / unknown objective / too-large guards."""
    with pytest.raises(SolverError, match="select_no_candidates"):
        select_ply_angles(_D0, np.array([]), 4)
    with pytest.raises(SolverError, match="select_nonpositive_plies"):
        select_ply_angles(_D0, _CANDS, 0)
    with pytest.raises(SolverError, match="select_unknown_objective"):
        select_ply_angles(_D0, _CANDS, 4, objective="bogus")
    with pytest.raises(SolverError, match="select_min_coupling_too_large"):
        select_ply_angles(_D0, _CANDS, 7, objective="min_coupling")
