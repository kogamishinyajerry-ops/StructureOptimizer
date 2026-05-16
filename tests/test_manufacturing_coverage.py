"""Wave X: targeted ``core/manufacturing.py`` coverage.

Hits the symmetry-x and extrusion edge cases the happy-path benchmark
suite doesn't exercise (most benchmarks use symmetry-y or no symmetry).
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.config import (
    ExtrusionConstraintConfig,
    SymmetryConstraintConfig,
)
from structure_optimizer.core.manufacturing import (
    apply_extrusion_projection,
    apply_symmetry_projection,
    evaluate_manufacturing_compliance,
    extrusion_residual,
    min_member_size_compliance,
    symmetry_residual,
)
from structure_optimizer.core.mesh import create_structured_mesh


@pytest.fixture
def small_mesh():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    return config, mesh


# ---------------------------------------------------------------------------
# Symmetry — x-axis branches (lines 85-91)
# ---------------------------------------------------------------------------


def test_apply_symmetry_x_axis_mirrors_left_right(small_mesh):
    _config, mesh = small_mesh
    rng = np.random.default_rng(0)
    densities = rng.uniform(0.1, 0.9, mesh.elements.shape[0])
    sym = SymmetryConstraintConfig(axis="x", position=0.5)
    projected = apply_symmetry_projection(mesh, densities, sym)

    grid = projected.reshape(mesh.nely, mesh.nelx)
    # After x-mirror at midline, columns ex and nelx-1-ex must match
    for ex in range(mesh.nelx // 2):
        mirror = mesh.nelx - 1 - ex
        np.testing.assert_allclose(grid[:, ex], grid[:, mirror], atol=1e-12)


def test_symmetry_residual_x_axis_zero_after_projection(small_mesh):
    _config, mesh = small_mesh
    rng = np.random.default_rng(1)
    densities = rng.uniform(0, 1, mesh.elements.shape[0])
    sym = SymmetryConstraintConfig(axis="x", position=0.5)
    projected = apply_symmetry_projection(mesh, densities, sym)
    assert symmetry_residual(mesh, projected, sym) < 1e-10


def test_symmetry_residual_y_axis_nonzero_on_asymmetric_field(small_mesh):
    """Asymmetric field should produce a positive residual."""
    _config, mesh = small_mesh
    densities = np.linspace(0.1, 0.9, mesh.elements.shape[0])
    sym = SymmetryConstraintConfig(axis="y", position=0.5)
    assert symmetry_residual(mesh, densities, sym) > 0


def test_symmetry_position_outside_mesh_leaves_field_unchanged(small_mesh):
    """A symmetry line far outside the mesh has no mirror cells to pair."""
    _config, mesh = small_mesh
    densities = np.linspace(0.1, 0.9, mesh.elements.shape[0])
    sym = SymmetryConstraintConfig(axis="y", position=10.0)  # well beyond mesh
    projected = apply_symmetry_projection(mesh, densities, sym)
    # No pairs → field is unchanged
    np.testing.assert_allclose(projected, densities, atol=1e-12)
    # Residual is also 0 (no paired cells)
    assert symmetry_residual(mesh, densities, sym) == 0.0


# ---------------------------------------------------------------------------
# Extrusion (lines 112-119, 151-156)
# ---------------------------------------------------------------------------


def test_apply_extrusion_x_axis_collapses_rows(small_mesh):
    _config, mesh = small_mesh
    rng = np.random.default_rng(2)
    densities = rng.uniform(0.1, 0.9, mesh.elements.shape[0])
    ext = ExtrusionConstraintConfig(axis="x")
    projected = apply_extrusion_projection(mesh, densities, ext)

    grid = projected.reshape(mesh.nely, mesh.nelx)
    # Each row should be constant
    for row in grid:
        np.testing.assert_allclose(row, row.mean(), atol=1e-12)


def test_apply_extrusion_y_axis_collapses_columns(small_mesh):
    _config, mesh = small_mesh
    rng = np.random.default_rng(3)
    densities = rng.uniform(0.1, 0.9, mesh.elements.shape[0])
    ext = ExtrusionConstraintConfig(axis="y")
    projected = apply_extrusion_projection(mesh, densities, ext)

    grid = projected.reshape(mesh.nely, mesh.nelx)
    # Each column should be constant
    for col in grid.T:
        np.testing.assert_allclose(col, col.mean(), atol=1e-12)


def test_extrusion_residual_x_zero_after_projection(small_mesh):
    _config, mesh = small_mesh
    rng = np.random.default_rng(4)
    densities = rng.uniform(0.1, 0.9, mesh.elements.shape[0])
    ext = ExtrusionConstraintConfig(axis="x")
    projected = apply_extrusion_projection(mesh, densities, ext)
    assert extrusion_residual(mesh, projected, ext) < 1e-10


def test_extrusion_residual_y_zero_after_projection(small_mesh):
    _config, mesh = small_mesh
    rng = np.random.default_rng(5)
    densities = rng.uniform(0.1, 0.9, mesh.elements.shape[0])
    ext = ExtrusionConstraintConfig(axis="y")
    projected = apply_extrusion_projection(mesh, densities, ext)
    assert extrusion_residual(mesh, projected, ext) < 1e-10


# ---------------------------------------------------------------------------
# min_member_size_compliance edge cases
# ---------------------------------------------------------------------------


def test_min_member_size_status_missing_when_not_declared(small_mesh):
    config, mesh = small_mesh
    # Cantilever smoke has no min_member_size declared
    report = min_member_size_compliance(config, mesh)
    assert report["status"] == "missing"


def test_min_member_size_status_passed_when_filter_large_enough(small_mesh):
    """Manually craft a config where filter_radius * cell_size > min_member_size."""
    from dataclasses import replace

    config, mesh = small_mesh
    new_mc = replace(config.manufacturing_constraints, min_member_size=0.5)
    new_config = replace(config, manufacturing_constraints=new_mc)
    report = min_member_size_compliance(new_config, mesh)
    assert report["status"] in {"passed", "warning"}
    assert "enforced_length" in report


# ---------------------------------------------------------------------------
# evaluate_manufacturing_compliance — exercises both branches
# ---------------------------------------------------------------------------


def test_evaluate_manufacturing_compliance_with_full_constraint_set(small_mesh):
    """All three constraints active should produce a 3-key report (lines 197-198, 210-211)."""
    from dataclasses import replace

    config, mesh = small_mesh
    sym = SymmetryConstraintConfig(axis="y", position=0.5)
    ext = ExtrusionConstraintConfig(axis="x")
    new_mc = replace(
        config.manufacturing_constraints,
        symmetry=sym,
        extrusion=ext,
        min_member_size=0.1,
    )
    new_config = replace(config, manufacturing_constraints=new_mc)
    densities = np.full(mesh.elements.shape[0], 0.5)
    report = evaluate_manufacturing_compliance(new_config, mesh, densities)
    assert "symmetry_compliance" in report
    assert "extrusion_compliance" in report
    assert "min_member_size_compliance" in report
    assert report["symmetry_compliance"]["status"] in {"passed", "warning", "missing"}
    assert report["extrusion_compliance"]["status"] in {"passed", "warning", "missing"}


def test_evaluate_manufacturing_compliance_no_constraints(small_mesh):
    """No constraints → all 'missing'."""
    config, mesh = small_mesh
    densities = np.full(mesh.elements.shape[0], 0.5)
    report = evaluate_manufacturing_compliance(config, mesh, densities)
    assert report["symmetry_compliance"]["status"] == "missing"
    assert report["extrusion_compliance"]["status"] == "missing"
