"""Wave U tests for linearized-buckling eigenvalue analysis."""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.buckling import (
    assemble_geometric_stiffness,
    buckling_load_factor,
    buckling_sensitivity,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.simp import run_simp


@pytest.fixture
def cantilever_solved():
    """Standard cantilever benchmark + a converged SIMP result."""
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    return config, mesh, result


def test_buckling_returns_positive_load_factor(cantilever_solved):
    """Stable design: λ_crit > 1 (load must be amplified to buckle)."""
    config, mesh, result = cantilever_solved
    lambdas, phis = buckling_load_factor(config, mesh, result.densities, result.final_analysis.displacements, n_modes=1)
    assert lambdas.shape == (1,)
    assert lambdas[0] > 1.0, f"expected stable design (λ>1), got λ={lambdas[0]}"
    assert phis.shape == (mesh.ndof, 1)
    # Eigenvector should be normalized in its free-DOF block
    norm = float(np.linalg.norm(phis[:, 0]))
    assert 0.9 < norm < 1.1


def test_buckling_multiple_modes_ordered_ascending(cantilever_solved):
    """λ_1 < λ_2 < λ_3 — first mode is the critical one."""
    config, mesh, result = cantilever_solved
    lambdas, _phis = buckling_load_factor(
        config, mesh, result.densities, result.final_analysis.displacements, n_modes=3
    )
    assert lambdas.shape == (3,)
    for i, j in itertools.pairwise(lambdas):
        assert i <= j + 1e-9


def test_buckling_sensitivity_shape_and_finiteness(cantilever_solved):
    """∂λ/∂ρ should have one entry per element and be finite."""
    config, mesh, result = cantilever_solved
    lambdas, phis = buckling_load_factor(config, mesh, result.densities, result.final_analysis.displacements, n_modes=1)
    sens = buckling_sensitivity(
        config,
        mesh,
        result.densities,
        result.final_analysis.displacements,
        float(lambdas[0]),
        phis[:, 0],
    )
    assert sens.shape == (mesh.elements.shape[0],)
    assert np.all(np.isfinite(sens))


def test_geometric_stiffness_symmetric(cantilever_solved):
    """K_g must be symmetric (so does the buckling solve)."""
    config, mesh, result = cantilever_solved
    Kg = assemble_geometric_stiffness(config, mesh, result.densities, result.final_analysis.displacements)
    asymmetry = float(np.max(np.abs(Kg - Kg.T)))
    assert asymmetry < 1e-8, f"K_g not symmetric: max |Kg - Kg.T| = {asymmetry}"


def test_buckling_higher_load_lower_factor(cantilever_solved):
    """Doubling the applied force halves the buckling load factor."""
    config, mesh, result = cantilever_solved
    # Original displacement field from the SIMP result
    u_base = result.final_analysis.displacements
    lam_base, _ = buckling_load_factor(config, mesh, result.densities, u_base, n_modes=1)
    # Scale displacement field by 2 (equivalent to doubling load since linear)
    lam_scaled, _ = buckling_load_factor(config, mesh, result.densities, 2.0 * u_base, n_modes=1)
    # K_g scales linearly with u, so λ should halve
    ratio = float(lam_scaled[0] / lam_base[0])
    assert abs(ratio - 0.5) < 0.05


def test_buckling_sensitivity_via_finite_difference(cantilever_solved):
    """Central-difference FD check on a mid-density element: sens ≈ Δλ/Δρ."""
    config, mesh, result = cantilever_solved
    densities = result.densities.copy()
    u = result.final_analysis.displacements

    lam0, phi0 = buckling_load_factor(config, mesh, densities, u, n_modes=1)
    sens = buckling_sensitivity(config, mesh, densities, u, float(lam0[0]), phi0[:, 0])

    # Restrict to elements with intermediate density so we can perturb both
    # directions without hitting bounds (∈ [0.1, 0.9])
    mid_mask = (densities > 0.1) & (densities < 0.9)
    candidate_ids = np.where(mid_mask & (np.abs(sens) > 1e-3))[0]
    if candidate_ids.size == 0:
        pytest.skip("no intermediate-density element with non-trivial sensitivity")
    # Pick the one with the largest |sens|
    eid = int(candidate_ids[np.argmax(np.abs(sens[candidate_ids]))])
    eps = 1e-3
    rho_minus = densities.copy()
    rho_minus[eid] -= eps
    rho_plus = densities.copy()
    rho_plus[eid] += eps
    # Same u throughout (analytical sens drops ∂u/∂ρ term — standard approx)
    lam_minus, _ = buckling_load_factor(config, mesh, rho_minus, u, n_modes=1)
    lam_plus, _ = buckling_load_factor(config, mesh, rho_plus, u, n_modes=1)
    fd = float((lam_plus[0] - lam_minus[0]) / (2 * eps))
    # Sign + magnitude check (order-of-magnitude — analytical is an
    # adjoint-free approximation per D019 caveat)
    if abs(sens[eid]) > 1e-3:
        ratio = fd / sens[eid]
        assert 0.05 < ratio < 20.0, f"FD/analytical sens ratio = {ratio:.3f} (sens={sens[eid]:.3e}, fd={fd:.3e})"
