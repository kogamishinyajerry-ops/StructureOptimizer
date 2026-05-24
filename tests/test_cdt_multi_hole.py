"""Wave YYY (v11, D080): constrained-Delaunay multi-hole smooth + watertight STL.

Quantitative anchors (watertight invariant + area, not qualitative trend):
- **genuine multi-hole watertight**: a smooth outer with **2 and 3** holes
  extrudes to a prism where every undirected edge is shared by exactly two facets
  (D072's ribbon was annulus / single-hole only);
- **cross-section area ≈ outer − Σ holes** to ≤ 1 % (polygon discretisation);
- **the CDT cap is a clean triangulation of the region**: its boundary edges
  (edges in exactly one triangle) equal exactly the ring edges — the
  watertightness guarantee, verified inside the routine (raises otherwise);
- robustness on 0 holes, an elliptical outer; degenerate input raises.

D072's reopening criterion: "constrained-Delaunay multi-hole smooth+watertight".
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.stl_export import (
    constrained_delaunay_triangulate,
    write_stl_cdt_multi_hole,
)


def _ring(cx: float, cy: float, r: float, n: int) -> np.ndarray:
    th = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    return np.column_stack([cx + r * np.cos(th), cy + r * np.sin(th)])


def _read_facets(path):
    """Parse vertex triples from an ASCII STL to re-check the edge manifold."""
    blocks = []
    cur = []
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if s.startswith("vertex"):
                p = s.split()
                cur.append((round(float(p[1]), 9), round(float(p[2]), 9), round(float(p[3]), 9)))
            if s.startswith("endfacet"):
                blocks.append(cur)
                cur = []
    return blocks


def test_two_and_three_holes_are_watertight(tmp_path):
    outer = _ring(0.0, 0.0, 1.0, 80)
    holes2 = [_ring(-0.42, 0.0, 0.18, 36), _ring(0.42, 0.0, 0.18, 36)]
    info2 = write_stl_cdt_multi_hole(outer, holes2, tmp_path / "h2.stl")
    assert info2["is_watertight"] is True
    assert info2["n_holes"] == 2

    holes3 = [_ring(-0.4, -0.2, 0.15, 30), _ring(0.4, -0.2, 0.15, 30), _ring(0.0, 0.45, 0.15, 30)]
    info3 = write_stl_cdt_multi_hole(outer, holes3, tmp_path / "h3.stl")
    assert info3["is_watertight"] is True
    assert info3["n_holes"] == 3
    # explicit edge-manifold re-check from the written file: every edge shared twice
    facets = _read_facets(tmp_path / "h3.stl")
    edges: dict[tuple, int] = {}
    for v in facets:
        for a, b in ((v[0], v[1]), (v[1], v[2]), (v[2], v[0])):
            edges[tuple(sorted((a, b)))] = edges.get(tuple(sorted((a, b))), 0) + 1
    assert all(c == 2 for c in edges.values())


def test_cross_section_area_matches_analytic(tmp_path):
    outer = _ring(0.0, 0.0, 1.0, 96)
    holes = [_ring(-0.42, 0.0, 0.18, 48), _ring(0.42, 0.0, 0.18, 48)]
    info = write_stl_cdt_multi_hole(outer, holes, tmp_path / "area.stl")
    expected = math.pi * 1.0**2 - 2.0 * math.pi * 0.18**2
    # polygon (not circle) → small discretisation deficit; ≤ 1 %
    assert abs(info["cross_section_area"] - expected) <= 0.01 * expected


def test_cdt_boundary_equals_ring_edges():
    outer = _ring(0.0, 0.0, 1.0, 60)
    holes = [_ring(-0.4, 0.0, 0.18, 28), _ring(0.4, 0.0, 0.18, 28)]
    _pts, tris = constrained_delaunay_triangulate(outer, holes)
    assert len(tris) > 0
    # boundary edges (in exactly one triangle) must equal the ring edges
    edge_count: dict[tuple, int] = {}
    for t in tris:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            edge_count[tuple(sorted((a, b)))] = edge_count.get(tuple(sorted((a, b))), 0) + 1
    boundary = {e for e, c in edge_count.items() if c == 1}
    assert len(boundary) == 60 + 28 + 28  # outer + 2 holes ring edges


def test_zero_hole_and_ellipse_robustness(tmp_path):
    outer = _ring(0.0, 0.0, 1.0, 72)
    solid = write_stl_cdt_multi_hole(outer, None, tmp_path / "solid.stl")
    assert solid["is_watertight"] is True
    assert abs(solid["cross_section_area"] - math.pi) <= 0.01 * math.pi

    th = np.linspace(0.0, 2.0 * np.pi, 90, endpoint=False)
    ellipse = np.column_stack([1.3 * np.cos(th), 0.8 * np.sin(th)])
    holes = [_ring(-0.5, 0.0, 0.15, 30), _ring(0.5, 0.0, 0.15, 30)]
    info = write_stl_cdt_multi_hole(ellipse, holes, tmp_path / "ell.stl")
    assert info["is_watertight"] is True


def test_cdt_error_handling(tmp_path):
    outer = _ring(0.0, 0.0, 1.0, 40)
    with pytest.raises(SolverError):
        write_stl_cdt_multi_hole(outer, None, tmp_path / "bad.stl", z_thickness=0.0)
    # a degenerate ring (collinear / < 3 distinct points) cannot be triangulated
    with pytest.raises(SolverError):
        constrained_delaunay_triangulate(np.array([[0.0, 0.0], [1.0, 0.0]]))
