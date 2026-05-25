"""Wave GGGG (v12, D088): flip-based CDT constraint recovery + min-angle refinement.

Quantitative anchors (closed form + manifold checks, not qualitative trend):
- on a non-convex polygon **D080 raises** ``cdt_constraint_recovery_failed`` while
  the flip-recovery **succeeds** with a watertight (2-manifold-capped) triangulation;
- **exact tiling**: the recovered triangle areas sum to the polygon area, and every
  constraint edge is present (boundary recovered);
- **min-angle refinement** is non-decreasing in the minimum angle, **strictly**
  improves it on a known case (18.75°→19.38°), and preserves area + constraints;
- on a convex polygon (no recovery needed) the recovery path **degenerates** to the
  same triangulation as D080.

D080's reopening criterion: "flip-based CDT constraint recovery + quality refinement".
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.stl_export import (
    _min_triangle_angle,
    _tri_area,
    _tri_sorted_edges,
    constrained_delaunay_flip_recover,
    constrained_delaunay_triangulate,
    polygon_area,
)

# 11-vertex star that the unconstrained Delaunay leaves a boundary edge out of
STAR = np.array([
    [2.6146, 0.045], [0.3886, 0.0405], [2.1953, 0.578], [-0.096, 0.7683],
    [-2.5324, -0.7121], [-1.381, -1.0942], [-0.1425, -1.1], [0.558, -1.3289],
    [0.1514, -0.3447], [0.5424, -0.3312], [1.9375, -0.8374],
])
# 10-vertex polygon where min-angle refinement strictly improves the worst angle
REFINE_POLY = np.array([
    [0.6641, 2.3816], [-0.6409, 0.9813], [-2.642, 0.8125], [-0.208, -0.6831],
    [0.2479, -0.9714], [0.9193, -1.8269], [1.9001, -1.3314], [0.3622, -0.2425],
    [0.9019, -0.489], [1.2678, -0.2709],
])


def _boundary_edges(tris):
    ct = {}
    for t in tris:
        for e in _tri_sorted_edges(t):
            ct[e] = ct.get(e, 0) + 1
    return {e for e, c in ct.items() if c == 1}, ct


def test_d080_fails_but_flip_recovery_succeeds_watertight():
    loop = [p for p in STAR]
    with pytest.raises(SolverError, match="cdt_constraint_recovery_failed"):
        constrained_delaunay_triangulate(loop)
    _pts, tris = constrained_delaunay_flip_recover(loop)
    assert len(tris) == len(STAR) - 2  # a simple polygon triangulates into n−2 triangles
    # 2-manifold cap: every edge is in 1 (boundary) or 2 (interior) triangles
    _, counts = _boundary_edges(tris)
    assert all(c in (1, 2) for c in counts.values())


def test_recovered_triangulation_tiles_exactly_and_recovers_all_constraints():
    loop = [p for p in STAR]
    pts, tris = constrained_delaunay_flip_recover(loop)
    # area conservation ⟺ exact tiling (no gaps / overlaps)
    assert abs(sum(_tri_area(pts[i], pts[j], pts[k]) for i, j, k in tris) - polygon_area(loop)) <= 1e-6
    # every boundary constraint edge (k,(k+1)%n) is present
    n = STAR.shape[0]
    present = {e for t in tris for e in _tri_sorted_edges(t)}
    for k in range(n):
        assert tuple(sorted((k, (k + 1) % n))) in present


def test_min_angle_refinement_strictly_improves_and_preserves():
    loop = [p for p in REFINE_POLY]
    p0, t0 = constrained_delaunay_flip_recover(loop, refine=False)
    p1, t1 = constrained_delaunay_flip_recover(loop, refine=True)
    a0, a1 = _min_triangle_angle(p0, t0), _min_triangle_angle(p1, t1)
    assert a1 > a0 + 1e-3, f"refinement did not strictly improve min angle ({np.rad2deg(a0):.2f}→{np.rad2deg(a1):.2f})"
    # refinement preserves the tiled area (no constraint flipped, still watertight)
    assert abs(sum(_tri_area(p1[i], p1[j], p1[k]) for i, j, k in t1) - polygon_area(loop)) <= 1e-6
    _, counts = _boundary_edges(t1)
    assert all(c in (1, 2) for c in counts.values())


def test_refinement_never_lowers_min_angle_on_star():
    loop = [p for p in STAR]
    a0 = _min_triangle_angle(*constrained_delaunay_flip_recover(loop, refine=False))
    a1 = _min_triangle_angle(*constrained_delaunay_flip_recover(loop, refine=True))
    assert a1 >= a0 - 1e-9


def test_convex_polygon_degenerates_to_d080():
    """No recovery needed ⟹ the flip-recovery path yields the same triangle set as
    D080 (both are the plain Delaunay of a convex region)."""
    loop = [np.array(p, float) for p in [(0, 0), (3, 0), (4, 2), (2, 4), (-1, 2)]]
    _, t_d080 = constrained_delaunay_triangulate(loop)
    _, t_ggg = constrained_delaunay_flip_recover(loop)

    def as_sets(tris):
        return {frozenset(t) for t in tris}

    assert as_sets(t_d080) == as_sets(t_ggg)


def test_recovery_with_a_hole_is_watertight():
    outer = [np.array(p, float) for p in [(-3, -3), (3, -3), (3, 3), (-3, 3)]]
    hole = [np.array(p, float) for p in [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]]
    pts, tris = constrained_delaunay_flip_recover(outer, [hole])
    _, counts = _boundary_edges(tris)
    assert all(c in (1, 2) for c in counts.values())
    # tiles the annular area (outer minus hole)
    area = sum(_tri_area(pts[i], pts[j], pts[k]) for i, j, k in tris)
    assert abs(area - (polygon_area(outer) - polygon_area(hole))) <= 1e-6
