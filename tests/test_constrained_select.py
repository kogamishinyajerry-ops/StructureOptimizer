"""Wave CCCCCCC (v15, D108) — constrained discrete angle selection (constrained_select).

Closes D102's reopening ("constrained selection so the max_bending optimum is no longer
the degenerate all-one-angle"). Quantitative anchors proving the constraint **truly
binds** (v15 discipline): (a) feasible + non-degenerate — balanced selection has
A₁₆=A₂₆=0 and ≥2 distinct angles; (b) it changes the design — unconstrained is the
degenerate all-one-angle with A₁₆≠0; (c) opt-in default reproduces D102 byte-exact. The
honest twist: balance costs **no** D_11 (Q̄₁₁ is even in θ).

Angles are in **radians**.
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.orthotropic_simp import (
    _constrained_select_balanced,
    orthotropic_plane_stress_matrix,
    select_ply_angles,
)

_D0 = orthotropic_plane_stress_matrix(e1=140e3, e2=10e3, nu12=0.3, g12=5e3)
_T = 0.125
_CAND = np.deg2rad([30.0, 60.0])  # no 0/π2 ⟹ the stiffest candidate is non-self-balanced


def _n_distinct(seq):
    return len({round(float(s), 6) for s in seq})


def test_constrained_select_feasible_and_non_degenerate():
    """(a) balanced=True ⟹ A₁₆=A₂₆=0 AND the design uses ≥2 distinct angles (±θ*)."""
    res = select_ply_angles(_D0, _CAND, 4, thickness=_T, objective="max_bending", balanced=True)
    assert abs(res.a_matrix[0, 2]) < 1e-7
    assert abs(res.a_matrix[1, 2]) < 1e-7
    assert _n_distinct(res.sequence) >= 2  # not the degenerate all-one-angle


def test_constraint_removes_degenerate_optimum():
    """(b) unconstrained is the degenerate all-one-angle (A₁₆≠0); the constraint binds."""
    raw = select_ply_angles(_D0, _CAND, 4, thickness=_T, objective="max_bending", balanced=False)
    bal = select_ply_angles(_D0, _CAND, 4, thickness=_T, objective="max_bending", balanced=True)
    assert _n_distinct(raw.sequence) == 1  # all-θ* (degenerate)
    assert abs(raw.a_matrix[0, 2]) > 1e3  # and unbalanced
    assert _n_distinct(bal.sequence) >= 2 and abs(bal.a_matrix[0, 2]) < 1e-7


def test_balance_costs_no_bending_stiffness():
    """The honest twist: D_11 is preserved (Q̄₁₁ even in θ) — balance is free for bending."""
    raw = select_ply_angles(_D0, _CAND, 4, thickness=_T, objective="max_bending", balanced=False)
    bal = select_ply_angles(_D0, _CAND, 4, thickness=_T, objective="max_bending", balanced=True)
    assert bal.d_matrix[0, 0] == pytest.approx(raw.d_matrix[0, 0], rel=1e-9)


def test_constrained_select_default_false_reproduces_d102():
    """(c) integration铁律: balanced=False reproduces D102 byte-exact."""
    cand = np.deg2rad([0.0, 45.0, 90.0])
    ref = select_ply_angles(_D0, cand, 4, thickness=_T, objective="max_bending")
    same = select_ply_angles(_D0, cand, 4, thickness=_T, objective="max_bending", balanced=False)
    assert np.array_equal(ref.sequence, same.sequence)
    assert np.array_equal(ref.d_matrix, same.d_matrix)
    assert ref.objective_value == same.objective_value


def test_constrained_select_min_coupling_reaches_zero():
    """min_coupling under the balanced constraint still reaches the ‖B‖=0 floor."""
    res = _constrained_select_balanced(_D0, _CAND, 4, _T, "min_coupling", False)
    assert res.objective_value < 1e-7
    assert float(np.linalg.norm(res.b_matrix)) < 1e-7


def test_constrained_select_guards():
    """No balanced multiset of odd size from off-axis candidates; too-large brute force."""
    with pytest.raises(SolverError, match="select_no_balanced_multiset"):
        select_ply_angles(_D0, _CAND, 3, thickness=_T, objective="max_bending", balanced=True)
    with pytest.raises(SolverError, match="select_min_coupling_too_large"):
        select_ply_angles(_D0, _CAND, 7, thickness=_T, objective="max_bending", balanced=True)
