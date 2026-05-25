"""Wave GGGGG (v13, D096) — Ruppert Delaunay refinement (Steiner insertion).

Quantitative analytical anchors (achieved min-angle bound / Lawson-can't-Ruppert-can
contrast), never qualitative trends. Traces D088's reopening criterion: "Ruppert
quality refinement (Steiner points at circumcentres) to guarantee a minimum-angle
lower bound — something Lawson flips on a fixed vertex set cannot do".

A high-aspect-ratio rectangle sampled at its corners only triangulates to ~14° min
angle; Lawson flips (a fixed 4-vertex set) are stuck there, but Ruppert inserts Steiner
points and lifts the minimum angle above the requested bound while staying watertight.
"""

from collections import Counter

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.stl_export import (
    _clean_ring,
    _min_triangle_angle,
    _tri_sorted_edges,
    constrained_delaunay_flip_recover,
    constrained_delaunay_ruppert,
    ruppert_refine,
)

# 4×1 rectangle: corner-only ⟹ min angle = atan(1/4) ≈ 14.04° (a slim triangle).
_RECT_4x1 = [[0.0, 0.0], [4.0, 0.0], [4.0, 1.0], [0.0, 1.0]]


def _min_angle_deg(pts, tris):
    return float(np.degrees(_min_triangle_angle(pts, tris)))


def _boundary_vertices_all_degree_two(tris):
    edge_count = Counter()
    for t in tris:
        for e in _tri_sorted_edges(t):
            edge_count[e] += 1
    deg = Counter()
    for e, c in edge_count.items():
        if c == 1:
            deg[e[0]] += 1
            deg[e[1]] += 1
    return all(v == 2 for v in deg.values()) and len(deg) > 0


def test_lawson_plateaus_but_ruppert_reaches_bound():
    """The headline: Lawson flips stay ~14°, Ruppert Steiner insertion clears ≥ 20°."""
    p_law, t_law = constrained_delaunay_flip_recover(_RECT_4x1, refine=True)
    assert _min_angle_deg(p_law, t_law) < 15.0  # Lawson on 4 fixed vertices is stuck
    p_rup, t_rup = constrained_delaunay_ruppert(_RECT_4x1, min_angle_deg=20.0)
    assert _min_angle_deg(p_rup, t_rup) >= 20.0


def test_steiner_points_added_and_original_corners_preserved():
    """Refinement only ADDS vertices; the four input corners are unchanged."""
    pts, _, _, n_steiner = ruppert_refine(
        list(_clean_ring(_RECT_4x1)),
        {(0, 1), (1, 2), (2, 3), (0, 3)},
        _clean_ring(_RECT_4x1),
        min_angle_deg=20.0,
    )
    assert n_steiner > 0
    assert pts.shape[0] == 4 + n_steiner
    assert np.allclose(pts[:4], _clean_ring(_RECT_4x1))  # corners untouched (prefix)


def test_refined_mesh_is_watertight():
    """Every boundary vertex still has degree 2 (closed loop) after refinement."""
    _p_rup, t_rup = constrained_delaunay_ruppert(_RECT_4x1, min_angle_deg=20.0)
    assert _boundary_vertices_all_degree_two(t_rup)
    # constrained_delaunay_ruppert itself raises if boundary ≠ subdivided constraints,
    # so reaching here already proves boundary == constraints.


def test_bound_achieved_for_several_thresholds():
    """For each safe bound the resulting minimum angle is ≥ that bound."""
    for bound in (10.0, 15.0, 20.0):
        p, t = constrained_delaunay_ruppert(_RECT_4x1, min_angle_deg=bound)
        assert _min_angle_deg(p, t) >= bound


def test_longer_sliver_needs_more_steiner_points():
    """A 6×1 rectangle (thinner ⟹ ~9.5° corner) needs more Steiner points than 4×1."""
    _, _, _, n4 = ruppert_refine(
        list(_clean_ring(_RECT_4x1)),
        {(0, 1), (1, 2), (2, 3), (0, 3)},
        _clean_ring(_RECT_4x1),
        min_angle_deg=20.0,
    )
    rect_6x1 = [[0.0, 0.0], [6.0, 0.0], [6.0, 1.0], [0.0, 1.0]]
    p6, t6, _, n6 = ruppert_refine(
        list(_clean_ring(rect_6x1)),
        {(0, 1), (1, 2), (2, 3), (0, 3)},
        _clean_ring(rect_6x1),
        min_angle_deg=20.0,
    )
    assert n6 > n4
    assert _min_angle_deg(p6, t6) >= 20.0


def test_ruppert_angle_bound_guard():
    """Bounds above the provably-terminating 20.7° (or ≤ 0) raise SolverError."""
    with pytest.raises(SolverError, match="ruppert_angle_bound_unsafe"):
        constrained_delaunay_ruppert(_RECT_4x1, min_angle_deg=35.0)
    with pytest.raises(SolverError, match="ruppert_angle_bound_unsafe"):
        constrained_delaunay_ruppert(_RECT_4x1, min_angle_deg=0.0)
