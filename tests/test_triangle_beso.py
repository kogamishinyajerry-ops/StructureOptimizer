"""Wave T tests for BESO on triangle meshes (closes D013 defer)."""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from structure_optimizer.core.triangle_beso import (
    TriangleBesoResult,
    run_beso_triangle,
)
from structure_optimizer.core.triangle_simp import split_quad_to_triangles


def _cantilever_setup(nelx=12, nely=6):
    mesh = split_quad_to_triangles(nelx, nely, width=2.0, height=1.0)
    left_nodes = np.where(mesh.nodes[:, 0] < 1e-9)[0]
    fixed_dofs = np.concatenate([[2 * n, 2 * n + 1] for n in left_nodes])
    right_mid = np.argmin(np.abs(mesh.nodes[:, 0] - 2.0) + np.abs(mesh.nodes[:, 1] - 0.5))
    force = np.zeros(mesh.ndof)
    force[2 * right_mid + 1] = -1.0
    return mesh, fixed_dofs, force


def test_beso_triangle_runs_and_returns_result():
    """Smoke: BESO on cantilever-shaped triangle mesh completes and returns binary densities."""
    mesh, fixed_dofs, force = _cantilever_setup()
    result = run_beso_triangle(
        mesh,
        young_modulus=1.0,
        poisson_ratio=0.3,
        fixed_dofs=fixed_dofs,
        force=force,
        volume_fraction=0.4,
        er=0.1,
        filter_radius=0.25,
        max_iterations=8,
        min_iterations=2,
    )
    assert isinstance(result, TriangleBesoResult)
    assert len(result.metrics) >= 1
    assert result.densities.shape == (mesh.n_elements,)
    # BESO is binary: densities should be in {min_density, 1.0}
    unique = sorted(set(result.densities))
    assert len(unique) <= 2
    for d in unique:
        assert d == pytest.approx(1e-3) or d == pytest.approx(1.0)


def test_beso_triangle_volume_walks_toward_target():
    """``current_target`` should decrease from 1.0 toward ``volume_fraction``."""
    mesh, fixed_dofs, force = _cantilever_setup()
    result = run_beso_triangle(
        mesh,
        young_modulus=1.0,
        poisson_ratio=0.3,
        fixed_dofs=fixed_dofs,
        force=force,
        volume_fraction=0.4,
        er=0.1,
        filter_radius=0.25,
        max_iterations=8,
        min_iterations=2,
    )
    # First target should be close to (1 - er)
    assert result.metrics[0].target_volume < 1.0
    # Targets must be monotonically non-increasing
    targets = [m.target_volume for m in result.metrics]
    for prev, curr in itertools.pairwise(targets):
        assert curr <= prev + 1e-9


def test_beso_triangle_baseline_compliance_below_final():
    """All-solid baseline must be stiffer (lower compliance) than reduced-material design."""
    mesh, fixed_dofs, force = _cantilever_setup()
    result = run_beso_triangle(
        mesh,
        young_modulus=1.0,
        poisson_ratio=0.3,
        fixed_dofs=fixed_dofs,
        force=force,
        volume_fraction=0.3,
        er=0.1,
        filter_radius=0.25,
        max_iterations=6,
        min_iterations=2,
    )
    assert result.final_compliance > result.baseline_compliance


def test_beso_triangle_raises_when_all_dofs_fixed():
    """Pathological: no free DOFs → SolverError."""
    from structure_optimizer.core.fem2d import SolverError

    mesh, _, _ = _cantilever_setup(nelx=2, nely=2)
    all_fixed = np.arange(mesh.ndof, dtype=int)
    force = np.zeros(mesh.ndof)
    with pytest.raises(SolverError, match="all degrees of freedom"):
        run_beso_triangle(
            mesh,
            young_modulus=1.0,
            poisson_ratio=0.3,
            fixed_dofs=all_fixed,
            force=force,
            volume_fraction=0.4,
            er=0.1,
            filter_radius=0.25,
            max_iterations=2,
            min_iterations=1,
        )


def test_beso_triangle_area_weighted_ranking_respects_unequal_areas():
    """On a deliberately non-uniform mesh, BESO should respect area weighting.

    Constructs a mesh where some triangles are twice the area of others;
    verifies the kept material's total area is close to target × design area.
    """
    from structure_optimizer.core.triangle import TriangleMesh

    # 4 triangles: 2 small (area 0.5) + 2 large (area 1.0)
    nodes = np.array(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [2.0, 0.0],
            [3.0, 0.0],
            [0.0, 1.0],
            [1.0, 1.0],
            [2.0, 2.0],
            [3.0, 2.0],
        ]
    )
    tris = np.array(
        [
            [0, 1, 4],  # small (area 0.5)
            [1, 5, 4],  # small (area 0.5)
            [1, 2, 5],  # small (area 0.5)
            [2, 6, 5],  # large (area 1.0)
            [2, 3, 6],  # large (area 1.0)
            [3, 7, 6],  # large (area 1.0)
        ]
    )
    mesh = TriangleMesh(nodes=nodes, elements=tris)
    # Fix the whole left edge — nodes 0 (0,0) and 4 (0,1), both x & y. Pinning
    # only node 0 leaves rigid-body rotation about it unconstrained, so the
    # global stiffness matrix is singular: Linux LAPACK raises LinAlgError
    # ("Singular matrix") while macOS Accelerate happened to tolerate it.
    # Constraining both left-edge nodes removes all rigid-body modes and matches
    # the cantilever intent (cf. _cantilever_setup, which fixes every x≈0 node).
    fixed_dofs = np.array([0, 1, 8, 9])
    force = np.zeros(mesh.ndof)
    force[2 * 3 + 1] = -1.0  # load at node 3

    result = run_beso_triangle(
        mesh,
        young_modulus=1.0,
        poisson_ratio=0.3,
        fixed_dofs=fixed_dofs,
        force=force,
        volume_fraction=0.5,
        er=0.2,
        filter_radius=0.5,
        max_iterations=8,
        min_iterations=2,
    )
    # Compute final area fraction
    areas = np.array([mesh.element_area(eid) for eid in range(mesh.n_elements)])
    total_area = float(areas.sum())
    kept_area = float(np.sum(areas[result.densities >= 0.5]))
    # Should be within 25% of target (small mesh + binary jumps make this loose)
    assert 0.25 <= kept_area / total_area <= 0.75
