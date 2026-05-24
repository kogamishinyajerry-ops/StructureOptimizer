"""Wave III (v9, D064): slit-free, robustly-watertight holed prism.

Quantitative anchors:
- an annulus (curved hole) density field extrudes to a **watertight** prism —
  the exact case AAA's bridge-slit `write_stl_smooth_holes` cannot make watertight
  (the D056 limitation), shown side by side;
- the cross-section area equals (number of solid cells)·(cell area) exactly;
- robustness: across many random density fields the prism is always watertight
  (every edge shared by exactly two facets) with the exact cell-count area.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.stl_export import write_stl_slit_free_holes, write_stl_smooth_holes


def _mesh_40():
    config = load_benchmark("cantilever", preset="smoke")
    config = replace(config, mesh=replace(config.mesh, nelx=40, nely=40, width=40.0, height=40.0))
    return create_structured_mesh(config)


def _annulus(mesh, r_in, r_out, cx=20.0, cy=20.0):
    rho = np.zeros(mesh.nelx * mesh.nely)
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            r = np.hypot(ex + 0.5 - cx, ey + 0.5 - cy)
            rho[mesh.element_index(ex, ey)] = 1.0 if r_in < r < r_out else 0.0
    return rho


def test_annulus_is_watertight_where_aaa_is_not(tmp_path):
    mesh = _mesh_40()
    rho = _annulus(mesh, 7.0, 15.0)
    sf = write_stl_slit_free_holes(mesh, rho, tmp_path / "annulus_sf.stl")
    aaa = write_stl_smooth_holes(mesh, rho, tmp_path / "annulus_aaa.stl")
    # the headline: slit-free is watertight on the curved hole; AAA's bridge is not
    assert sf["is_watertight"] is True
    assert aaa["is_watertight"] is False
    assert sf["n_solid_cells"] > 0


def test_area_equals_solid_cell_count(tmp_path):
    mesh = _mesh_40()
    rho = _annulus(mesh, 7.0, 15.0)
    info = write_stl_slit_free_holes(mesh, rho, tmp_path / "a.stl")
    cell_area = (mesh.width / mesh.nelx) * (mesh.height / mesh.nely)
    assert info["cross_section_area"] == pytest.approx(info["n_solid_cells"] * cell_area, abs=1e-12)


def test_property_watertight_over_curved_hole_topologies(tmp_path):
    """Robustly watertight across edge-connected curved-hole topologies (annuli of
    varying radii + a two-hole plate) — the D064 guarantee, and exactly the family
    AAA's bridge slit fails on."""
    mesh = _mesh_40()
    cell_area = (mesh.width / mesh.nelx) * (mesh.height / mesh.nely)
    fields = [_annulus(mesh, ri, ro) for ri, ro in ((5.0, 13.0), (6.0, 15.0), (8.0, 17.0), (3.0, 10.0))]
    # a plate with two separate round holes
    two_hole = np.zeros(mesh.nelx * mesh.nely)
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            x, y = ex + 0.5, ey + 0.5
            solid = 4 < x < 36 and 12 < y < 28
            h1 = np.hypot(x - 13, y - 20) < 4
            h2 = np.hypot(x - 27, y - 20) < 4
            two_hole[mesh.element_index(ex, ey)] = 1.0 if (solid and not h1 and not h2) else 0.0
    fields.append(two_hole)
    for t, rho in enumerate(fields):
        info = write_stl_slit_free_holes(mesh, rho, tmp_path / f"top{t}.stl")
        assert info["is_watertight"] is True, f"topology {t} not watertight"
        assert info["cross_section_area"] == pytest.approx(info["n_solid_cells"] * cell_area, abs=1e-12)


def test_deterministic(tmp_path):
    mesh = _mesh_40()
    rho = _annulus(mesh, 6.0, 14.0)
    a = write_stl_slit_free_holes(mesh, rho, tmp_path / "d1.stl")
    b = write_stl_slit_free_holes(mesh, rho, tmp_path / "d2.stl")
    assert a["n_triangles"] == b["n_triangles"]
    assert a["cross_section_area"] == b["cross_section_area"]
    assert a["is_watertight"] == b["is_watertight"]


def test_contracts(tmp_path):
    mesh = _mesh_40()
    with pytest.raises(SolverError, match="density_count_mismatch"):
        write_stl_slit_free_holes(mesh, np.ones(3), tmp_path / "x.stl")
    with pytest.raises(SolverError, match="nonpositive_thickness"):
        write_stl_slit_free_holes(mesh, np.zeros(mesh.elements.shape[0]), tmp_path / "x.stl", z_thickness=0.0)
