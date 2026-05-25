"""Wave FFFFFF (v14, D103) — Ruppert concentric-shell small-input-angle handling.

Quantitative analytical anchors (termination independent of max_steiner, exact
backward-compat byte reproduction on non-acute input, achieved angle bound away from the
apex, watertightness), never qualitative trends. Traces D096's reopening criterion:
"small-input-angle handling (concentric-shell)".

v14 integration铁律: concentric_shells is opt-in (default False); on a non-acute input
the flag is a no-op and the triangulation is byte-identical to D096's midpoint Ruppert.
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.stl_export import (
    _apex_locked,
    _clean_ring,
    _min_triangle_angle,
    _small_angle_apexes,
    constrained_delaunay_ruppert,
    ruppert_refine,
)

# A 30×10 body with a sharp (~4.8°) leftward spike apex at index 4 — the small input
# angle that defeats plain midpoint Ruppert.
_SPIKE = np.array([[0.0, 0.0], [30.0, 0.0], [30.0, 10.0], [0.0, 10.0], [-120.0, 5.0]])
_SQUARE = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]])  # no small angle


def _refine(poly, shells, cap):
    outer = _clean_ring(poly)
    ptl = [np.asarray(p, dtype=float) for p in outer]
    cons: set[tuple[int, int]] = set()
    m = outer.shape[0]
    for k in range(m):
        cons.add(tuple(sorted((k, (k + 1) % m))))
    return outer, cons, ruppert_refine(
        ptl, set(cons), outer, [], min_angle_deg=20.0, max_steiner=cap, concentric_shells=shells
    )


def test_concentric_shell_terminates_independent_of_budget():
    """With shells, n_steiner is the same at max_steiner=300 and 600 ⟹ refinement
    TERMINATED naturally, not on the max_steiner backstop."""
    _, _, (_, _, _, ns300) = _refine(_SPIKE, True, 300)
    _, _, (_, _, _, ns600) = _refine(_SPIKE, True, 600)
    assert ns300 == ns600  # stable ⟹ converged, not budget-limited
    assert ns300 < 300  # did not exhaust the backstop


def test_plain_midpoint_fails_on_acute_input():
    """The contrast: plain midpoint Ruppert (shells=False) cannot make the acute input
    watertight — the public API raises (the defect D096 deferred)."""
    with pytest.raises(SolverError, match="ruppert_not_watertight"):
        constrained_delaunay_ruppert(_SPIKE, min_angle_deg=20.0, max_steiner=300, concentric_shells=False)


def test_concentric_shell_watertight_and_angle_bound_away_from_apex():
    """shells=True: public API returns a watertight cap whose triangles meet the 20°
    bound everywhere EXCEPT the unavoidable apex wedge (geometry, not a bug)."""
    pts, tris = constrained_delaunay_ruppert(_SPIKE, min_angle_deg=20.0, max_steiner=400, concentric_shells=True)
    outer = _clean_ring(_SPIKE)
    cons: set[tuple[int, int]] = set()
    m = outer.shape[0]
    for k in range(m):
        cons.add(tuple(sorted((k, (k + 1) % m))))
    apex = _small_angle_apexes([np.asarray(p, dtype=float) for p in outer], cons, np.radians(60.0))
    # the public API already verified watertightness (else it raised); confirm the bound
    # holds on every non-apex-locked triangle.
    nonlock = [t for t in tris if not _apex_locked(t, apex, set(cons))]
    assert nonlock  # there is a refinable bulk region
    assert np.degrees(_min_triangle_angle(pts, nonlock)) >= 20.0 - 1e-6


def test_backward_compat_byte_exact_on_non_acute_input():
    """v14 integration anchor: on a square (no small angle) the opt-in flag is a no-op —
    shells=True reproduces shells=False byte-for-byte (apex set empty ⟹ midpoint path)."""
    _, _, (p_false, t_false, c_false, ns_false) = _refine(_SQUARE, False, 200)
    _, _, (p_true, t_true, c_true, ns_true) = _refine(_SQUARE, True, 200)
    assert np.array_equal(p_false, p_true)
    assert t_false == t_true
    assert c_false == c_true
    assert ns_false == ns_true


def test_small_angle_apex_detection():
    """_small_angle_apexes flags only sub-threshold corners: the spike apex, not a
    90° square corner."""
    outer = _clean_ring(_SPIKE)
    cons: set[tuple[int, int]] = set()
    m = outer.shape[0]
    for k in range(m):
        cons.add(tuple(sorted((k, (k + 1) % m))))
    apex = _small_angle_apexes([np.asarray(p, dtype=float) for p in outer], cons, np.radians(60.0))
    assert apex == {4}  # only the sharp spike vertex
    sq = _clean_ring(_SQUARE)
    sc: set[tuple[int, int]] = set()
    for k in range(sq.shape[0]):
        sc.add(tuple(sorted((k, (k + 1) % sq.shape[0]))))
    assert _small_angle_apexes([np.asarray(p, dtype=float) for p in sq], sc, np.radians(60.0)) == set()


def test_ruppert_angle_bound_guard_still_holds_with_shells():
    """The min-angle safety guard is unchanged when shells are enabled."""
    with pytest.raises(SolverError, match="ruppert_angle_bound_unsafe"):
        constrained_delaunay_ruppert(_SQUARE, min_angle_deg=25.0, concentric_shells=True)
