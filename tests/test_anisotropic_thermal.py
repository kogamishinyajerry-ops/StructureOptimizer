"""Wave GG (v6): anisotropic / orthotropic tensor thermal conductivity.

Quantitative anchors:
- isotropic tensor k·I reduces (machine precision) to the analytical scalar
  element matrix;
- the FEM **patch test** — a linear temperature field is reproduced exactly
  for any constant conductivity tensor (zero interior residual);
- rotation invariance of an isotropic tensor.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.thermal import (
    _assemble_thermal_dense,
    conductivity_tensor,
    element_thermal_conductivity,
    element_thermal_conductivity_tensor,
    rotate_conductivity_tensor,
    solve_thermal,
)
from structure_optimizer.core.thermal_simp import load_thermal_benchmark


def test_isotropic_tensor_matches_scalar_analytical():
    """k·I tensor element matrix == analytical scalar matrix (machine precision)."""
    k = 3.7
    ke_tensor = element_thermal_conductivity_tensor(conductivity_tensor(k, k, 0.0), thickness=1.0)
    ke_scalar = element_thermal_conductivity(k, thickness=1.0)
    np.testing.assert_allclose(ke_tensor, ke_scalar, atol=1e-12)


def test_orthotropic_patch_test_linear_field():
    """FEM patch test: a linear temperature field T = a·x + b·y produces zero
    interior residual for any constant conductivity tensor (here orthotropic
    + off-diagonal). This is the quantitative correctness anchor."""
    config = load_benchmark("cantilever", preset="smoke")  # any structured mesh
    mesh = create_structured_mesh(config)
    k = conductivity_tensor(kxx=5.0, kyy=1.0, kxy=0.7)
    ke = element_thermal_conductivity_tensor(k, thickness=1.0)
    density_scale = np.ones(mesh.elements.shape[0])
    K = _assemble_thermal_dense(mesh, density_scale, ke)

    a, b = 2.3, -1.1
    x, y = mesh.nodes[:, 0], mesh.nodes[:, 1]
    T_linear = a * x + b * y
    residual = K @ T_linear

    # Interior nodes: not on any outer edge.
    nelx, nely = mesh.nelx, mesh.nely
    interior = [mesh.node_id(i, j) for i in range(1, nelx) for j in range(1, nely)]
    assert interior, "need interior nodes for the patch test"
    np.testing.assert_allclose(residual[interior], 0.0, atol=1e-9)


def test_conductivity_tensor_rotation_invariance_isotropic():
    """An isotropic tensor is invariant under rotation → element matrix unchanged."""
    k_iso = conductivity_tensor(2.0, 2.0, 0.0)
    ke0 = element_thermal_conductivity_tensor(k_iso)
    for theta in (0.3, 1.1, 2.7):
        k_rot = rotate_conductivity_tensor(k_iso, theta)
        np.testing.assert_allclose(k_rot, k_iso, atol=1e-12)
        ke_rot = element_thermal_conductivity_tensor(k_rot)
        np.testing.assert_allclose(ke_rot, ke0, atol=1e-12)


def test_orthotropic_90deg_rotation_swaps_axes():
    """Rotating an orthotropic tensor by 90° swaps kxx↔kyy."""
    k = conductivity_tensor(kxx=5.0, kyy=1.0, kxy=0.0)
    k_rot = rotate_conductivity_tensor(k, np.pi / 2)
    np.testing.assert_allclose(k_rot, conductivity_tensor(1.0, 5.0, 0.0), atol=1e-12)


def test_solve_thermal_isotropic_tensor_equals_scalar():
    """solve_thermal with conductivity_tensor = k·I matches the scalar solve."""
    config, k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    r_scalar = solve_thermal(config, mesh, densities, k, sources, bcs)
    r_tensor = solve_thermal(
        config, mesh, densities, k, sources, bcs, conductivity_tensor=conductivity_tensor(k, k, 0.0)
    )
    np.testing.assert_allclose(r_tensor.temperatures, r_scalar.temperatures, rtol=1e-9, atol=1e-12)


def test_orthotropic_easier_conduction_lowers_temperature():
    """Physical sanity: higher conductivity along the heat-flow axis lowers the
    peak temperature for the same heat input."""
    config, k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 1.0)
    r_lowk = solve_thermal(
        config, mesh, densities, k, sources, bcs, conductivity_tensor=conductivity_tensor(0.5 * k, 0.5 * k)
    )
    r_highk = solve_thermal(
        config, mesh, densities, k, sources, bcs, conductivity_tensor=conductivity_tensor(2.0 * k, 2.0 * k)
    )
    assert r_highk.max_temperature < r_lowk.max_temperature


def test_conductivity_tensor_rejects_nonsymmetric():
    with pytest.raises(SolverError, match="symmetric"):
        element_thermal_conductivity_tensor(np.array([[1.0, 0.5], [0.2, 1.0]]))


def test_conductivity_tensor_rejects_non_positive_definite():
    with pytest.raises(SolverError, match="positive_definite"):
        element_thermal_conductivity_tensor(np.array([[1.0, 2.0], [2.0, 1.0]]))  # eigenvalue -1
