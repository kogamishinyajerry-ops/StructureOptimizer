"""Wave FFFFF (v13, D095) — laminate stacking-sequence optimisation.

Quantitative analytical anchors (rearrangement-inequality global optimum / exact
symmetric decoupling), never qualitative trends. Traces D087's reopening criterion:
"connect laminate_abd to a stacking-sequence optimisation (discrete ply angles,
symmetric/balanced constraints)".

- ``max_bending`` is the **rearrangement-inequality** optimum (stiffest plies at the
  high-bending-leverage surfaces) ⟹ it equals the brute-force global maximum exactly.
- ``symmetric=True`` builds a mid-plane-symmetric laminate ⟹ coupling ``B = 0`` exactly.
- ``min_coupling`` exhaustively finds the ‖B‖-minimal ordering, reaching 0 when a
  symmetric arrangement of the inventory exists.
"""

from itertools import permutations

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.orthotropic_simp import (
    laminate_abd,
    optimize_stacking_sequence,
    orthotropic_plane_stress_matrix,
)

# A carbon-fibre-ish orthotropic lamina (E1 ≫ E2) so 0° is much stiffer than 90°.
_D0 = orthotropic_plane_stress_matrix(e1=140e3, e2=10e3, nu12=0.3, g12=5e3)
_T = 0.125


def _abd(seq):
    return laminate_abd(_D0, np.asarray(seq, dtype=float), np.full(len(seq), _T))


def _d11(seq):
    return _abd(seq)[2][0, 0]


def _bnorm(seq):
    return float(np.linalg.norm(_abd(seq)[1]))


def test_max_bending_equals_bruteforce_global_optimum():
    """Rearrangement-inequality ordering = the brute-force max D_11 over all orderings."""
    inv = [0.0, 0.0, 45.0, 90.0, -45.0, 90.0]
    res = optimize_stacking_sequence(_D0, np.array(inv), _T, objective="max_bending")
    brute = max(permutations(inv), key=lambda s: _d11(list(s)))
    assert res.objective_value == pytest.approx(_d11(list(brute)), rel=1e-9)
    assert res.objective_value == pytest.approx(_d11(res.sequence), rel=1e-12)


def test_max_bending_puts_stiffest_plies_at_surfaces():
    """The optimum places the stiffest (0°) plies at the outer surfaces."""
    inv = np.array([0.0, 90.0, 90.0, 0.0, 90.0, 0.0])
    res = optimize_stacking_sequence(_D0, inv, _T, objective="max_bending")
    # surfaces are positions 0 and n−1; both should be the stiffest angle (0°)
    assert res.sequence[0] == pytest.approx(0.0)
    assert res.sequence[-1] == pytest.approx(0.0)
    # and the mid-plane plies should be the softest (90°)
    mid = res.sequence.size // 2
    assert res.sequence[mid] == pytest.approx(90.0)


def test_symmetric_gives_zero_coupling_exactly():
    """A mid-plane-symmetric stack (half + reversed half) has B = 0 to machine precision."""
    half = np.array([0.0, 45.0, 90.0])
    res = optimize_stacking_sequence(_D0, half, _T, objective="max_bending", symmetric=True)
    assert np.linalg.norm(res.b_matrix) < 1e-9
    # full stack is the half mirrored about the mid-plane
    assert np.allclose(res.sequence, np.concatenate([res.sequence[:3], res.sequence[:3][::-1]]))
    # and bending D_11 is positive / matches a direct ABD of the built sequence
    assert res.objective_value == pytest.approx(_d11(res.sequence), rel=1e-12)


def test_min_coupling_equals_bruteforce_and_reaches_zero():
    """min_coupling finds the ‖B‖-minimal ordering; an inventory with a symmetric
    arrangement reaches ‖B‖ = 0."""
    inv = [0.0, 0.0, 90.0, 90.0]
    res = optimize_stacking_sequence(_D0, np.array(inv), _T, objective="min_coupling")
    brute = min(permutations(inv), key=lambda s: _bnorm(list(s)))
    assert res.objective_value == pytest.approx(_bnorm(list(brute)), abs=1e-12)
    assert res.objective_value < 1e-9  # symmetric arrangement [0,90,90,0] exists


def test_min_coupling_beats_a_bad_ordering():
    """The optimised coupling is far below a deliberately unsymmetric stacking."""
    inv = [0.0, 0.0, 90.0, 90.0]
    res = optimize_stacking_sequence(_D0, np.array(inv), _T, objective="min_coupling")
    bad = _bnorm([0.0, 0.0, 90.0, 90.0])  # all 0° on one side ⟹ large coupling
    assert bad > 1e3  # this stacking is strongly coupled
    assert res.objective_value < 1e-6 * bad


def test_stacking_guards():
    """Empty / nonpositive-thickness / unknown-objective / oversized brute-force raise."""
    with pytest.raises(SolverError, match="stacking_no_plies"):
        optimize_stacking_sequence(_D0, np.array([]), _T)
    with pytest.raises(SolverError, match="stacking_nonpositive_thickness"):
        optimize_stacking_sequence(_D0, np.array([0.0, 90.0]), 0.0)
    with pytest.raises(SolverError, match="stacking_unknown_objective"):
        optimize_stacking_sequence(_D0, np.array([0.0, 90.0]), _T, objective="bad")
    with pytest.raises(SolverError, match="stacking_min_coupling_too_many_plies"):
        optimize_stacking_sequence(_D0, np.arange(9.0), _T, objective="min_coupling")
