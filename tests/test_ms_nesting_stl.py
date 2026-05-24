"""Wave AAA (v8, D056): marching-squares nested loops → ear-clipping caps + holes.

Quantitative anchors:
- ``classify_loops_even_odd`` detects nesting exactly: a square inside a square is
  one group with one hole; two disjoint squares are two groups with no holes; a
  triply-nested set is an outer-with-hole plus a solid island (2 groups);
- ``write_stl_smooth_holes`` carves the hole so the cap area equals
  (outer ring area − hole ring area) **exactly** — area conservation;
- a clean-cornered (rectangular) hole produces a **watertight** STL.

Honest scope (see D056): the zero-width bridge slit used to cut a hole open is
non-manifold for high-vertex *curved* holes (an annulus), so watertight is
asserted only for the clean-cornered case; area conservation holds for both.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.stl_export import (
    classify_loops_even_odd,
    marching_squares_contours,
    polygon_area,
    write_stl_smooth_holes,
)


def _square(cx, cy, half):
    return [(cx - half, cy - half), (cx + half, cy - half),
            (cx + half, cy + half), (cx - half, cy + half)]


def test_even_odd_nesting_detection():
    # nested: small square inside big square → 1 group, 1 hole
    groups = classify_loops_even_odd([_square(10, 10, 10), _square(10, 10, 4)])
    assert len(groups) == 1
    assert len(groups[0][1]) == 1
    # disjoint: two separate squares → 2 groups, no holes
    g2 = classify_loops_even_odd([_square(2.5, 2.5, 2.5), _square(12.5, 12.5, 2.5)])
    assert len(g2) == 2
    assert [len(holes) for _, holes in g2] == [0, 0]
    # triple-nest: outer ⊃ middle ⊃ inner → outer-with-hole + solid island
    g3 = classify_loops_even_odd([_square(15, 15, 15), _square(15, 15, 10), _square(15, 15, 5)])
    assert len(g3) == 2
    assert sorted(len(holes) for _, holes in g3) == [0, 1]


def _holed_field(mesh, hole_lo, hole_hi):
    """Solid block [6,34]² with a rectangular hole, on the cell-centre grid."""
    nelx, nely = mesh.nelx, mesh.nely
    rho = np.zeros(nelx * nely)
    for ey in range(nely):
        for ex in range(nelx):
            x, y = ex + 0.5, ey + 0.5
            solid = 6 < x < 34 and 6 < y < 34
            hole = hole_lo < x < hole_hi and hole_lo < y < hole_hi
            rho[mesh.element_index(ex, ey)] = 1.0 if (solid and not hole) else 0.0
    return rho


def _mesh_40():
    config = load_benchmark("cantilever", preset="smoke")
    from dataclasses import replace
    config = replace(config, mesh=replace(config.mesh, nelx=40, nely=40, width=40.0, height=40.0))
    return create_structured_mesh(config)


def _expected_holed_area(mesh, rho, rho_threshold=0.5):
    """Independent (outer − hole) area straight from the MS loops + nesting."""
    cell_w = mesh.width / mesh.nelx
    cell_h = mesh.height / mesh.nely
    field = np.zeros((mesh.nely, mesh.nelx))
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            field[ey, ex] = rho[mesh.element_index(ex, ey)]
    x_coords = (np.arange(mesh.nelx) + 0.5) * cell_w
    y_coords = (np.arange(mesh.nely) + 0.5) * cell_h
    loops = [lp for lp in marching_squares_contours(field, x_coords, y_coords, rho_threshold)
             if polygon_area(lp) > 1e-12]
    groups = classify_loops_even_odd(loops)
    area = 0.0
    for outer, holes in groups:
        area += polygon_area(outer) - sum(polygon_area(h) for h in holes)
    return area, len(groups)


def test_rectangular_hole_is_watertight_and_area_exact(tmp_path):
    mesh = _mesh_40()
    rho = _holed_field(mesh, 15, 25)
    info = write_stl_smooth_holes(mesh, rho, tmp_path / "rect_hole.stl")
    expected_area, expected_groups = _expected_holed_area(mesh, rho)
    assert info["n_groups"] == expected_groups == 1
    # cap area == outer − hole, exact
    assert info["cross_section_area"] == pytest.approx(expected_area, abs=1e-9)
    # clean-cornered hole → watertight 2.5D prism
    assert info["is_watertight"] is True
    assert info["n_triangles"] > 0


def test_annulus_area_conservation(tmp_path):
    # curved (many-vertex) hole: area conservation still exact even though the
    # zero-width bridge slit is non-manifold (watertight not claimed — D056).
    mesh = _mesh_40()
    nelx, nely = mesh.nelx, mesh.nely
    rho = np.zeros(nelx * nely)
    cx = cy = 20.0
    for ey in range(nely):
        for ex in range(nelx):
            r = np.hypot(ex + 0.5 - cx, ey + 0.5 - cy)
            rho[mesh.element_index(ex, ey)] = 1.0 if 7.0 < r < 15.0 else 0.0
    info = write_stl_smooth_holes(mesh, rho, tmp_path / "annulus.stl")
    expected_area, expected_groups = _expected_holed_area(mesh, rho)
    assert info["n_groups"] == expected_groups == 1
    assert info["cross_section_area"] == pytest.approx(expected_area, abs=1e-9)


def test_contracts(tmp_path):
    mesh = _mesh_40()
    with pytest.raises(SolverError, match="density_count_mismatch"):
        write_stl_smooth_holes(mesh, np.ones(3), tmp_path / "x.stl")
    with pytest.raises(SolverError, match="nonpositive_thickness"):
        write_stl_smooth_holes(mesh, np.zeros(mesh.elements.shape[0]),
                               tmp_path / "x.stl", z_thickness=0.0)
