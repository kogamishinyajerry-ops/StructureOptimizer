"""Wave AAAAAAAA (v16, D114) — anti-symmetric ordering constraint embedded in
optimize_stacking_sequence (closes D110's reopening).

D110 built the anti-symmetric laminate as a standalone construction; this wave embeds it
*inside* the production stacking optimiser (the bending-side analogue of D106's balanced
embed). Quantitative analytical anchors, never qualitative trends.

v16 deep-embedding discipline: (a) bending_shear_decoupled=True ⟹ the OPTIMISED stack has
D₁₆=D₂₆=0 (feasible + new semantics); (b) the constraint CHANGES the optimum vs the plain
path (binding); (c) bending_shear_decoupled=False reproduces the D095/D106 path
byte-for-byte (opt-in default).

Angles are in **radians**.
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.orthotropic_simp import (
    make_antisymmetric_laminate,
    optimize_stacking_sequence,
    orthotropic_plane_stress_matrix,
)

_D0 = orthotropic_plane_stress_matrix(e1=140e3, e2=10e3, nu12=0.3, g12=5e3)
_HALF = np.deg2rad([15.0, 40.0, 65.0])  # a 3-ply half-stack inventory
_T = 0.125


def test_embedded_optimum_zeros_bending_shear():
    """Headline: the optimiser's output with bending_shear_decoupled=True has D₁₆=D₂₆=0
    exactly — the decoupling is now a property of the *optimised* laminate."""
    res = optimize_stacking_sequence(_D0, _HALF, _T, objective="max_bending", bending_shear_decoupled=True)
    assert res.d_matrix[0, 2] == pytest.approx(0.0, abs=1e-7)
    assert res.d_matrix[1, 2] == pytest.approx(0.0, abs=1e-7)


def test_embedded_optimum_is_also_balanced():
    """Anti-symmetry also zeros the extensional shear coupling A₁₆=A₂₆ in the output."""
    res = optimize_stacking_sequence(_D0, _HALF, _T, objective="max_bending", bending_shear_decoupled=True)
    assert res.a_matrix[0, 2] == pytest.approx(0.0, abs=1e-7)
    assert res.a_matrix[1, 2] == pytest.approx(0.0, abs=1e-7)


def test_constraint_changes_the_optimum():
    """Binding evidence: the plain optimiser (no constraint) on the same inventory keeps
    D₁₆≠0 — the constraint genuinely changes the optimised laminate."""
    plain = optimize_stacking_sequence(_D0, _HALF, _T, objective="max_bending")
    assert abs(plain.d_matrix[0, 2]) > 1e2  # unconstrained optimum has bending-shear coupling
    decoupled = optimize_stacking_sequence(_D0, _HALF, _T, objective="max_bending", bending_shear_decoupled=True)
    assert abs(decoupled.d_matrix[0, 2]) < 1e-7
    # and the stacks genuinely differ (different length too: anti-sym doubles the half)
    assert decoupled.sequence.size == 2 * plain.sequence.size


def test_default_false_byte_exact_reproduces_plain():
    """Opt-in default: bending_shear_decoupled=False reproduces the no-flag (D095/D106)
    result byte-for-byte — the new parameter does not perturb the existing path."""
    a = optimize_stacking_sequence(_D0, _HALF, _T, objective="max_bending")
    b = optimize_stacking_sequence(_D0, _HALF, _T, objective="max_bending", bending_shear_decoupled=False)
    assert np.array_equal(a.sequence, b.sequence)
    assert a.objective_value == b.objective_value


def test_rearrangement_is_global_max_among_antisymmetric_orderings():
    """max_bending: the rearrangement (stiffest half-ply at the surface) gives the global
    maximum D_11 among ALL anti-symmetric orderings of the half-stack — because Q̄_11 is
    even in θ, no other anti-symmetric arrangement beats it."""
    res = optimize_stacking_sequence(_D0, _HALF, _T, objective="max_bending", bending_shear_decoupled=True)
    from itertools import permutations
    best_brute = -np.inf
    for perm in {tuple(p) for p in permutations(_HALF.tolist())}:
        stack = make_antisymmetric_laminate(np.array(perm))
        from structure_optimizer.core.orthotropic_simp import laminate_abd
        _, _, d = laminate_abd(_D0, stack, np.full(stack.size, _T))
        best_brute = max(best_brute, float(d[0, 0]))
    assert res.objective_value == pytest.approx(best_brute, abs=1e-9)


def test_antisym_embed_guards():
    """Anti-symmetry is mutually exclusive with symmetric/balanced (its own construction,
    already balanced); empty plies guard."""
    with pytest.raises(SolverError, match="stacking_antisym_exclusive"):
        optimize_stacking_sequence(_D0, _HALF, _T, symmetric=True, bending_shear_decoupled=True)
    with pytest.raises(SolverError, match="stacking_antisym_exclusive"):
        optimize_stacking_sequence(_D0, _HALF, _T, balanced=True, bending_shear_decoupled=True)
    with pytest.raises(SolverError, match="stacking_no_plies"):
        optimize_stacking_sequence(_D0, np.array([]), _T, bending_shear_decoupled=True)
