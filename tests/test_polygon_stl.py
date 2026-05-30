"""Wave SS (v7, D048): ear-clipping general-polygon STL + holes.

Quantitative anchors:
- ear clipping conserves area exactly on concave / non-star-convex polygons
  (≤1e-12), where the old centroid-fan cap gives the wrong area;
- a holed polygon (even-odd nesting) triangulates to outer − hole area (≤1e-12);
- the extruded prism is watertight (every edge shared by exactly two facets).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.stl_export import (
    _tri_area,
    ear_clipping_triangulate,
    polygon_area,
    triangulate_with_holes,
    write_stl_polygon,
)

L_SHAPE = [(0.0, 0.0), (4.0, 0.0), (4.0, 1.0), (1.0, 1.0), (1.0, 4.0), (0.0, 4.0)]


def _star(n_points=5, r_out=2.0, r_in=0.8):
    pts = []
    for t in range(2 * n_points):
        r = r_out if t % 2 == 0 else r_in
        ang = math.pi / 2 + t * math.pi / n_points
        pts.append((r * math.cos(ang), r * math.sin(ang)))
    return pts


def _tri_sum(pts, tris):
    return sum(_tri_area(pts[i], pts[j], pts[k]) for i, j, k in tris)


def test_ear_clipping_conserves_area_concave():
    pts, tris = ear_clipping_triangulate(L_SHAPE)
    true_area = polygon_area([np.asarray(p, float) for p in L_SHAPE])
    assert _tri_sum(pts, tris) == pytest.approx(true_area, abs=1e-12)
    assert len(tris) == len(L_SHAPE) - 2  # a simple polygon yields n−2 triangles


def test_ear_clipping_conserves_area_star():
    star = _star()
    pts, tris = ear_clipping_triangulate(star)
    true_area = polygon_area([np.asarray(p, float) for p in star])
    assert _tri_sum(pts, tris) == pytest.approx(true_area, abs=1e-12)
    assert len(tris) == len(star) - 2


def test_centroid_fan_is_wrong_on_concave_polygon():
    # The old marching-squares cap fans from the centroid; for a non-star-convex
    # polygon that over/under-counts area — the reason ear clipping is needed.
    pts = np.asarray(L_SHAPE, float)
    cen = pts.mean(axis=0)
    fan = sum(_tri_area(cen, pts[k], pts[(k + 1) % len(pts)]) for k in range(len(pts)))
    true_area = polygon_area([np.asarray(p, float) for p in L_SHAPE])
    assert abs(fan - true_area) > 1.0  # demonstrably wrong (11 vs 7)
    # ear clipping gets it exactly
    e_pts, e_tris = ear_clipping_triangulate(L_SHAPE)
    assert _tri_sum(e_pts, e_tris) == pytest.approx(true_area, abs=1e-12)


def test_holes_even_odd_area_conservation():
    outer = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    hole = [(3.0, 3.0), (7.0, 3.0), (7.0, 7.0), (3.0, 7.0)]
    pts, tris = triangulate_with_holes(outer, [hole])
    assert _tri_sum(pts, tris) == pytest.approx(100.0 - 16.0, abs=1e-12)


def test_two_holes_area_conservation():
    outer = [(0.0, 0.0), (12.0, 0.0), (12.0, 6.0), (0.0, 6.0)]
    h1 = [(1.0, 1.0), (3.0, 1.0), (3.0, 5.0), (1.0, 5.0)]  # area 8
    h2 = [(8.0, 2.0), (10.0, 2.0), (10.0, 4.0), (8.0, 4.0)]  # area 4
    pts, tris = triangulate_with_holes(outer, [h1, h2])
    assert _tri_sum(pts, tris) == pytest.approx(72.0 - 8.0 - 4.0, abs=1e-12)


def test_extruded_concave_prism_is_watertight(tmp_path):
    info = write_stl_polygon(_star(), tmp_path / "star.stl", z_thickness=1.5)
    assert info["is_watertight"]
    assert info["cross_section_area"] == pytest.approx(polygon_area([np.asarray(p, float) for p in _star()]), abs=1e-12)


def test_extruded_holed_prism_is_watertight_and_area_exact(tmp_path):
    outer = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    hole = [(3.0, 3.0), (7.0, 3.0), (7.0, 7.0), (3.0, 7.0)]
    info = write_stl_polygon(outer, tmp_path / "holed.stl", holes=[hole], z_thickness=2.0)
    assert info["is_watertight"]
    assert info["cross_section_area"] == pytest.approx(84.0, abs=1e-12)


def test_property_earclip_area_conservation():
    """Property: ear clipping conserves area for random simple (convex) polygons."""
    rng = np.random.default_rng(99)
    for _ in range(25):
        n = int(rng.integers(3, 9))
        pts = rng.uniform(-5, 5, size=(n, 2))
        # sort by angle about the centroid → a simple (convex) polygon
        cen = pts.mean(axis=0)
        order = np.argsort(np.arctan2(pts[:, 1] - cen[1], pts[:, 0] - cen[0]))
        loop = [tuple(p) for p in pts[order]]
        true_area = polygon_area([np.asarray(p, float) for p in loop])
        if true_area < 1e-6:
            continue
        e_pts, tris = ear_clipping_triangulate(loop)
        assert _tri_sum(e_pts, tris) == pytest.approx(true_area, abs=1e-12)


def test_contracts(tmp_path):
    with pytest.raises(SolverError, match="degenerate_polygon"):
        ear_clipping_triangulate([(0.0, 0.0), (1.0, 1.0)])
    with pytest.raises(SolverError, match="nonpositive_thickness"):
        write_stl_polygon(L_SHAPE, tmp_path / "bad.stl", z_thickness=0.0)
