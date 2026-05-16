"""Wave DD: 2D → STL boundary export tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.stl_export import write_stl


@pytest.fixture
def small_mesh():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    return config, mesh


def test_write_stl_creates_valid_ascii_file(small_mesh):
    config, mesh = small_mesh
    densities = np.full(mesh.elements.shape[0], 0.7)  # all solid (above 0.5)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        path = Path(f.name)
    try:
        info = write_stl(mesh, densities, str(path), rho_threshold=0.5)
        content = path.read_text()
        # ASCII STL must start with `solid <name>` and end with `endsolid <name>`
        assert content.startswith("solid topology")
        assert content.rstrip().endswith("endsolid topology")
        assert "facet normal" in content
        assert "outer loop" in content
        assert "vertex" in content
        assert "endloop" in content
        assert "endfacet" in content
        # Should have 12 triangles per cell × n_cells
        n_solid = info["n_solid_cells"]
        assert info["n_triangles"] == 12 * n_solid
    finally:
        path.unlink()


def test_write_stl_skips_void_cells(small_mesh):
    config, mesh = small_mesh
    densities = np.full(mesh.elements.shape[0], 0.0)  # all void
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        path = Path(f.name)
    try:
        info = write_stl(mesh, densities, str(path), rho_threshold=0.5)
        assert info["n_solid_cells"] == 0
        assert info["n_triangles"] == 0
        content = path.read_text()
        assert "facet normal" not in content
    finally:
        path.unlink()


def test_write_stl_respects_threshold(small_mesh):
    config, mesh = small_mesh
    n_elem = mesh.elements.shape[0]
    densities = np.linspace(0.0, 1.0, n_elem)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        path = Path(f.name)
    try:
        info_low = write_stl(mesh, densities, str(path), rho_threshold=0.3)
        info_high = write_stl(mesh, densities, str(path), rho_threshold=0.8)
        # Higher threshold → fewer solid cells
        assert info_low["n_solid_cells"] > info_high["n_solid_cells"]
    finally:
        path.unlink()


def test_write_stl_rejects_density_mismatch(small_mesh):
    config, mesh = small_mesh
    bad = np.zeros(mesh.elements.shape[0] + 1)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        path = Path(f.name)
    try:
        with pytest.raises(SolverError, match="density_count_mismatch"):
            write_stl(mesh, bad, str(path))
    finally:
        path.unlink()


def test_write_stl_rejects_nonpositive_thickness(small_mesh):
    config, mesh = small_mesh
    densities = np.full(mesh.elements.shape[0], 1.0)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        path = Path(f.name)
    try:
        with pytest.raises(SolverError, match="nonpositive_thickness"):
            write_stl(mesh, densities, str(path), z_thickness=0.0)
    finally:
        path.unlink()


def test_property_stl_triangle_count_is_12_per_solid_cell(small_mesh):
    """Every solid axis-aligned box contributes exactly 12 triangles
    (6 faces × 2)."""
    config, mesh = small_mesh
    n_elem = mesh.elements.shape[0]
    densities = np.random.default_rng(0).uniform(0.0, 1.0, n_elem)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        path = Path(f.name)
    try:
        info = write_stl(mesh, densities, str(path), rho_threshold=0.5)
        assert info["n_triangles"] == 12 * info["n_solid_cells"]
    finally:
        path.unlink()
