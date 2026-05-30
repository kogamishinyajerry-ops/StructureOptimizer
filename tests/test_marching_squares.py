"""Wave JJ (v6): marching-squares smooth-boundary STL.

Quantitative anchors:
- For a smooth field (a disk level set) the marching-squares enclosed area
  converges to the exact area as O(h²) and beats the voxel (staircase) area,
  whose error is O(h).
- Every interior contour loop is closed (first point ≈ last point).
"""

from __future__ import annotations

from math import pi

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.stl_export import (
    marching_squares_contours,
    polygon_area,
    write_stl_marching_squares,
)

R, CX, CY = 0.3, 0.5, 0.5
EXACT_AREA = pi * R * R


def _disk_field(n: int):
    """Smooth disk level set on an n×n grid of the unit square; level = 0."""
    xs = np.linspace(0.0, 1.0, n)
    ys = np.linspace(0.0, 1.0, n)
    X, Y = np.meshgrid(xs, ys)  # X[j, i] = xs[i]
    field = R * R - ((X - CX) ** 2 + (Y - CY) ** 2)
    return field, xs, ys


def _ms_area(n: int) -> float:
    field, xs, ys = _disk_field(n)
    loops = marching_squares_contours(field, xs, ys, level=0.0)
    return sum(polygon_area(lp) for lp in loops)


def _voxel_area(n: int) -> float:
    field, xs, _ = _disk_field(n)
    h = xs[1] - xs[0]
    return float((field > 0.0).sum()) * h * h


def test_disk_area_second_order_convergence():
    err1 = abs(_ms_area(65) - EXACT_AREA)
    err2 = abs(_ms_area(129) - EXACT_AREA)  # halve h
    # O(h²) → error roughly quarters; demand clearly better than O(h)'s ½.
    assert err2 < 0.45 * err1, f"not 2nd-order: err1={err1:.2e} err2={err2:.2e}"
    assert err2 / EXACT_AREA < 0.005, f"fine-grid area error too large: {err2 / EXACT_AREA:.4f}"


def test_marching_squares_beats_voxel():
    n = 65
    ms_err = abs(_ms_area(n) - EXACT_AREA)
    voxel_err = abs(_voxel_area(n) - EXACT_AREA)
    assert ms_err < voxel_err, f"ms_err={ms_err:.2e} not below voxel_err={voxel_err:.2e}"


def test_contours_are_closed():
    field, xs, ys = _disk_field(49)
    loops = marching_squares_contours(field, xs, ys, level=0.0)
    big = [lp for lp in loops if polygon_area(lp) > 1e-9]
    assert len(big) == 1, f"expected one disk loop, got {len(big)}"
    loop = big[0]
    assert np.allclose(loop[0], loop[-1]), "contour loop is not closed"


def test_polygon_area_unit_square_exact():
    square = [np.array([0.0, 0.0]), np.array([2.0, 0.0]), np.array([2.0, 3.0]), np.array([0.0, 3.0])]
    assert polygon_area(square) == pytest.approx(6.0, abs=1e-12)


def test_marching_squares_grid_too_small_rejected():
    with pytest.raises(SolverError, match="grid_too_small"):
        marching_squares_contours(np.zeros((1, 5)), np.arange(5.0), np.arange(1.0))
    with pytest.raises(SolverError, match="coord_mismatch"):
        marching_squares_contours(np.zeros((3, 3)), np.arange(4.0), np.arange(3.0))


def test_write_stl_marching_squares_valid_ascii():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    # disk-shaped solid region in the centre of the domain
    densities = np.zeros(mesh.elements.shape[0])
    cw, ch = mesh.width / mesh.nelx, mesh.height / mesh.nely
    rad = 0.35 * min(mesh.width, mesh.height)
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            xc, yc = (ex + 0.5) * cw, (ey + 0.5) * ch
            if (xc - mesh.width / 2) ** 2 + (yc - mesh.height / 2) ** 2 < rad * rad:
                densities[mesh.element_index(ex, ey)] = 1.0

    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        path = Path(f.name)
    try:
        info = write_stl_marching_squares(mesh, densities, str(path), rho_threshold=0.5)
        content = path.read_text()
        assert content.startswith("solid topology_smooth")
        assert content.rstrip().endswith("endsolid topology_smooth")
        assert "facet normal" in content and "vertex" in content
        assert info["n_loops"] >= 1
        assert info["cross_section_area"] > 0
        # 4 triangles per contour segment (2 wall + bottom cap + top cap).
        assert info["n_triangles"] % 4 == 0
        assert content.count("facet normal") == info["n_triangles"]
    finally:
        path.unlink(missing_ok=True)


def test_write_stl_marching_squares_density_mismatch():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    with pytest.raises(SolverError, match="density_count_mismatch"):
        write_stl_marching_squares(mesh, np.zeros(3), "/tmp/none.stl")
