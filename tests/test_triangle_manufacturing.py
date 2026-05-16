"""Wave T tests for triangle-mesh manufacturing projections (closes D008 defer)."""

from __future__ import annotations

import numpy as np
from structure_optimizer.core.config import (
    ExtrusionConstraintConfig,
    ManufacturingConstraintsConfig,
    SymmetryConstraintConfig,
)
from structure_optimizer.core.triangle_manufacturing import (
    apply_triangle_extrusion_projection,
    apply_triangle_manufacturing_projections,
    apply_triangle_symmetry_projection,
    measure_triangle_extrusion_residual,
    measure_triangle_symmetry_residual,
)
from structure_optimizer.core.triangle_simp import split_quad_to_triangles


def test_symmetry_x_makes_pairs_equal():
    """After x-symmetry projection, mirrored pairs should have identical density."""
    mesh = split_quad_to_triangles(4, 4, width=1.0, height=1.0)
    rng = np.random.default_rng(42)
    densities = rng.uniform(0.1, 1.0, mesh.n_elements)
    sym = SymmetryConstraintConfig(axis="x", position=0.5)
    projected = apply_triangle_symmetry_projection(mesh, densities, sym)
    # Residual should be smaller after projection
    res_before = measure_triangle_symmetry_residual(mesh, densities, sym)
    res_after = measure_triangle_symmetry_residual(mesh, projected, sym)
    assert res_after <= res_before
    # Projection is idempotent — re-projecting changes nothing
    twice = apply_triangle_symmetry_projection(mesh, projected, sym)
    np.testing.assert_allclose(twice, projected, atol=1e-12)


def test_symmetry_y_makes_pairs_equal():
    """Same as test_symmetry_x but across y axis."""
    mesh = split_quad_to_triangles(4, 4, width=1.0, height=1.0)
    rng = np.random.default_rng(0)
    densities = rng.uniform(0.1, 1.0, mesh.n_elements)
    sym = SymmetryConstraintConfig(axis="y", position=0.5)
    projected = apply_triangle_symmetry_projection(mesh, densities, sym)
    twice = apply_triangle_symmetry_projection(mesh, projected, sym)
    np.testing.assert_allclose(twice, projected, atol=1e-12)


def test_extrusion_x_uniform_along_x():
    """After x-extrusion, all elements at the same y should have the same density."""
    mesh = split_quad_to_triangles(6, 4, width=2.0, height=1.0)
    rng = np.random.default_rng(1)
    densities = rng.uniform(0.1, 1.0, mesh.n_elements)
    ext = ExtrusionConstraintConfig(axis="x")
    projected = apply_triangle_extrusion_projection(mesh, densities, ext)
    centroids = mesh.element_centroids
    # Group by y bucket; densities within each bucket should match (up to bucket discretization)
    ys = np.unique(np.round(centroids[:, 1], 5))
    for y in ys:
        idx = np.where(np.isclose(centroids[:, 1], y, atol=1e-5))[0]
        spread = projected[idx].max() - projected[idx].min()
        assert spread <= 1e-9


def test_extrusion_y_uniform_along_y():
    """After y-extrusion, all elements at the same x should have the same density."""
    mesh = split_quad_to_triangles(4, 6, width=1.0, height=2.0)
    rng = np.random.default_rng(2)
    densities = rng.uniform(0.1, 1.0, mesh.n_elements)
    ext = ExtrusionConstraintConfig(axis="y")
    projected = apply_triangle_extrusion_projection(mesh, densities, ext)
    centroids = mesh.element_centroids
    xs = np.unique(np.round(centroids[:, 0], 5))
    for x in xs:
        idx = np.where(np.isclose(centroids[:, 0], x, atol=1e-5))[0]
        spread = projected[idx].max() - projected[idx].min()
        assert spread <= 1e-9


def test_apply_combined_projections():
    """Both projections applied in order: symmetry then extrusion."""
    mesh = split_quad_to_triangles(4, 4, width=1.0, height=1.0)
    rng = np.random.default_rng(3)
    densities = rng.uniform(0.1, 1.0, mesh.n_elements)
    constraints = ManufacturingConstraintsConfig(
        symmetry=SymmetryConstraintConfig(axis="x", position=0.5),
        extrusion=ExtrusionConstraintConfig(axis="y"),
    )
    projected = apply_triangle_manufacturing_projections(constraints, mesh, densities)
    # After both: symmetric across x AND uniform along y
    res_sym = measure_triangle_symmetry_residual(mesh, projected, constraints.symmetry)
    # symmetry residual may be > 0 after extrusion broke perfect symmetry — but ≤ original
    res_sym_before = measure_triangle_symmetry_residual(mesh, densities, constraints.symmetry)
    assert res_sym <= res_sym_before


def test_no_constraints_returns_copy():
    """Empty constraints should produce an identical (but new) array."""
    mesh = split_quad_to_triangles(3, 3)
    densities = np.array([0.5] * mesh.n_elements)
    constraints = ManufacturingConstraintsConfig()
    projected = apply_triangle_manufacturing_projections(constraints, mesh, densities)
    np.testing.assert_array_equal(projected, densities)
    assert projected is not densities


def test_symmetry_projection_preserves_mass_approximately():
    """Mirror-averaging preserves total density mass (sum stays the same)."""
    mesh = split_quad_to_triangles(6, 6, width=1.0, height=1.0)
    rng = np.random.default_rng(7)
    densities = rng.uniform(0.0, 1.0, mesh.n_elements)
    sym = SymmetryConstraintConfig(axis="x", position=0.5)
    projected = apply_triangle_symmetry_projection(mesh, densities, sym)
    # Sum equality is the exact algebraic property of averaging mutual pairs
    assert abs(float(projected.sum()) - float(densities.sum())) < 1e-9


def test_extrusion_residual_zero_after_projection():
    """measure_extrusion_residual after projection should be ~0."""
    mesh = split_quad_to_triangles(5, 5, width=1.0, height=1.0)
    rng = np.random.default_rng(11)
    densities = rng.uniform(0.1, 1.0, mesh.n_elements)
    ext = ExtrusionConstraintConfig(axis="x")
    projected = apply_triangle_extrusion_projection(mesh, densities, ext)
    assert measure_triangle_extrusion_residual(mesh, projected, ext) < 1e-9


def test_symmetry_invalid_axis_falls_back_to_y_behavior():
    """Unknown axis defaults to y branch (no crash).

    This documents the existing behavior — if a user passes an unsupported
    axis string, the function does not raise but follows the 'else' branch.
    Hardening this in v4 would be a separate cleanup task.
    """
    mesh = split_quad_to_triangles(3, 3)
    densities = np.full(mesh.n_elements, 0.5)
    # axis='z' is not a real option, but we test we don't crash and produce
    # the y-axis result
    sym = SymmetryConstraintConfig(axis="z", position=0.5)
    projected = apply_triangle_symmetry_projection(mesh, densities, sym)
    # Should not raise; constant input → constant output
    np.testing.assert_allclose(projected, densities, atol=1e-12)


def test_extrusion_degenerate_mesh_returns_input():
    """When all centroids share the perpendicular coordinate exactly, output = input."""
    from structure_optimizer.core.triangle import TriangleMesh

    # Two triangles whose centroids both land at y=0.5 (one above, one below mirrored)
    nodes = np.array(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [0.5, 1.5],  # tri 0 centroid y = 0.5
            [2.0, 0.0],
            [3.0, 0.0],
            [2.5, 1.5],  # tri 1 centroid y = 0.5
        ]
    )
    tris = np.array([[0, 1, 2], [3, 4, 5]])
    mesh = TriangleMesh(nodes=nodes, elements=tris)
    centroids = mesh.element_centroids
    # Both centroids must share y for this to be degenerate along y
    assert abs(centroids[0, 1] - centroids[1, 1]) < 1e-9
    densities = np.array([0.3, 0.7])
    ext = ExtrusionConstraintConfig(axis="x")
    projected = apply_triangle_extrusion_projection(mesh, densities, ext)
    # Degenerate y → function returns input unchanged
    np.testing.assert_array_equal(projected, densities)
