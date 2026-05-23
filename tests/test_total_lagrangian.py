"""Wave EE (v6): full Total-Lagrangian Green-strain Newton tests.

The flagship correctness checks are *quantitative against analytical results*,
not the v5 "qualitative trend" bar:

1. **Objectivity / frame indifference** — a finite rigid-body rotation produces
   *zero* Green-Lagrange strain to machine precision. This is the property the
   v5 ``K + ½K_g`` approximation does NOT satisfy; it is the whole point of the
   full TL upgrade (rubric §2.4).
2. **Constant-strain patch** — a uniform stretch λ gives E11 = ½(λ²−1) exactly.
3. **Linear limit** — at tiny load the TL solve matches the linear FEM solve.
4. **Geometric stiffening** — at the working load the TL tip displacement does
   not exceed the linear estimate (elastica sub-linear trend).
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError, solve_linear_elastic
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.total_lagrangian import (
    green_strain_field,
    solve_total_lagrangian,
)


@pytest.fixture
def cantilever_smoke():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    return config, mesh


# --- quantitative analytical correctness (the v6 upgrade) -----------------


def test_finite_rotation_zero_green_strain(cantilever_smoke):
    """Objectivity: a 30° rigid-body rotation → zero Green strain everywhere.

    For u = (R − I) X the deformation gradient is exactly R, so
    E = ½(RᵀR − I) = 0. The full TL must satisfy this to machine precision.
    """
    _config, mesh = cantilever_smoke
    theta = np.deg2rad(30.0)
    rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    X = mesh.nodes  # (n_nodes, 2)
    x_new = X @ rot.T
    u = (x_new - X).reshape(-1)  # interleaved [u0x,u0y,...]
    E = green_strain_field(mesh, u)
    assert np.allclose(E, 0.0, atol=1e-10), f"rigid rotation produced nonzero Green strain: max={np.abs(E).max():.2e}"


def test_uniform_stretch_green_strain_matches_analytical(cantilever_smoke):
    """Constant-strain patch: uniform stretch λ in x → E11 = ½(λ²−1) exactly."""
    _config, mesh = cantilever_smoke
    lam = 1.2
    X = mesh.nodes
    u = np.zeros_like(X)
    u[:, 0] = (lam - 1.0) * X[:, 0]  # u_x = (λ−1) x
    E = green_strain_field(mesh, u.reshape(-1))
    expected = 0.5 * (lam**2 - 1.0)
    np.testing.assert_allclose(E[:, 0], expected, atol=1e-12, err_msg="E11 != ½(λ²−1)")
    np.testing.assert_allclose(E[:, 1], 0.0, atol=1e-12)
    np.testing.assert_allclose(E[:, 2], 0.0, atol=1e-12)


def test_total_lagrangian_small_load_agrees_with_linear(cantilever_smoke):
    """Linear limit: at tiny load TL displacement matches linear FEM."""
    config, mesh = cantilever_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    tiny_loads = []
    for ld in config.loads:
        t = dict(ld)
        t["fx"] = 1e-4 * float(ld.get("fx", 0.0))
        t["fy"] = 1e-4 * float(ld.get("fy", 0.0))
        tiny_loads.append(t)
    config_tiny = replace(config, loads=tiny_loads)
    r_lin = solve_linear_elastic(config_tiny, mesh, densities)
    r_tl = solve_total_lagrangian(config_tiny, mesh, densities, n_load_steps=1, max_inner_iter=10)
    max_dof = int(np.argmax(np.abs(r_lin.displacements)))
    rel = abs(r_tl.displacements[max_dof] - r_lin.displacements[max_dof]) / abs(r_lin.displacements[max_dof])
    assert rel < 1e-3, f"TL linear-limit mismatch: rel={rel:.2e}"


def test_total_lagrangian_geometric_stiffening_vs_linear(cantilever_smoke):
    """At the working load the TL tip displacement does not exceed linear
    (geometric stiffening — elastica sub-linear trend)."""
    config, mesh = cantilever_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    r_lin = solve_linear_elastic(config, mesh, densities)
    r_tl = solve_total_lagrangian(config, mesh, densities, n_load_steps=5, max_inner_iter=25)
    assert r_tl.converged, "TL did not converge at working load"
    u_lin = float(np.max(np.abs(r_lin.displacements)))
    u_tl = float(np.max(np.abs(r_tl.displacements)))
    assert u_tl <= u_lin * 1.02, f"TL ({u_tl:.4e}) should not exceed linear ({u_lin:.4e})"


# --- robustness / contracts -----------------------------------------------


def test_total_lagrangian_zero_load_zero_displacement(cantilever_smoke):
    config, mesh = cantilever_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    zero_loads = [dict(ld, fx=0.0, fy=0.0) for ld in config.loads]
    config_zero = replace(config, loads=zero_loads)
    r = solve_total_lagrangian(config_zero, mesh, densities, n_load_steps=2)
    assert np.allclose(r.displacements, 0.0)
    assert r.converged


def test_total_lagrangian_density_count_mismatch_raises(cantilever_smoke):
    config, mesh = cantilever_smoke
    with pytest.raises(SolverError, match="density_count_mismatch"):
        solve_total_lagrangian(config, mesh, np.ones(mesh.elements.shape[0] + 3))


def test_total_lagrangian_rejects_nonpositive_load_steps(cantilever_smoke):
    config, mesh = cantilever_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    with pytest.raises(SolverError, match="n_load_steps_must_be_positive"):
        solve_total_lagrangian(config, mesh, densities, n_load_steps=0)


def test_property_total_lagrangian_strain_energy_nonnegative(cantilever_smoke):
    """Property: strain energy ∫½S:E dV ≥ 0 for the SVK material at convergence."""
    config, mesh = cantilever_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    r = solve_total_lagrangian(config, mesh, densities, n_load_steps=3, max_inner_iter=20)
    assert r.strain_energy >= -1e-12, f"negative strain energy: {r.strain_energy}"
    assert np.isfinite(r.displacements).all()
