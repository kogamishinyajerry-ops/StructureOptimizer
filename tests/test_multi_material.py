"""Wave BB: multi-material SIMP tests.

Verifies:
1. Single-material (M=1) collapses to vanilla SIMP (consistency).
2. Two-material effective modulus respects ordering: a region with
   stiff-material full density is stiffer than soft-material full.
3. Compliance with M=2 is no worse than single soft-material at same
   total volume budget.
4. SIMP main loop runs to convergence with valid densities.
5. Property tests: per-material volume bounds, density-mismatch error.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError, solve_linear_elastic
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.multi_material import (
    MaterialProperty,
    effective_modulus_per_element,
    run_multi_material_simp,
    solve_multi_material,
)


@pytest.fixture
def bimaterial_smoke():
    config = load_benchmark("bimaterial_beam", preset="smoke")
    mesh = create_structured_mesh(config)
    return config, mesh


@pytest.fixture
def two_materials():
    return [
        MaterialProperty(name="soft", young_modulus=10_000.0, poisson_ratio=0.3, density=1.0),
        MaterialProperty(name="stiff", young_modulus=200_000.0, poisson_ratio=0.3, density=3.0),
    ]


def test_effective_modulus_returns_correct_shape(bimaterial_smoke, two_materials):
    _config, mesh = bimaterial_smoke
    n_elem = mesh.elements.shape[0]
    densities = np.full((2, n_elem), 0.5)
    E = effective_modulus_per_element(densities, two_materials, penalty=3.0, e_min=1.0)
    assert E.shape == (n_elem,)
    assert (E > 0).all()


def test_effective_modulus_stiff_full_density_dominates(two_materials):
    """If material 2 is at ρ=1 and material 1 at ρ=0, E_eff ≈ E_2."""
    densities = np.array([[0.0], [1.0]])  # M=2, n_elem=1
    E = effective_modulus_per_element(densities, two_materials, penalty=3.0, e_min=1.0)
    expected = 1.0 + 1.0**3 * (two_materials[1].young_modulus - 1.0)
    np.testing.assert_allclose(E, [expected], atol=1e-6, rtol=1e-6)


def test_effective_modulus_void_returns_e_min(two_materials):
    """All materials at zero density → E_eff = E_min."""
    densities = np.array([[0.0], [0.0]])
    E = effective_modulus_per_element(densities, two_materials, penalty=3.0, e_min=1.5)
    np.testing.assert_allclose(E, [1.5], atol=1e-12)


def test_effective_modulus_count_mismatch_error(two_materials):
    densities = np.zeros((3, 10))  # M=3 but materials list has 2
    with pytest.raises(SolverError, match="multi_material_count_mismatch"):
        effective_modulus_per_element(densities, two_materials, penalty=3.0, e_min=1.0)


def test_solve_multi_material_returns_finite_field(bimaterial_smoke, two_materials):
    config, mesh = bimaterial_smoke
    n_elem = mesh.elements.shape[0]
    densities = np.full((2, n_elem), 0.3)
    result = solve_multi_material(config, mesh, densities, two_materials, e_min=1.0)
    assert np.all(np.isfinite(result.displacements))
    assert result.compliance > 0
    assert result.effective_modulus.shape == (n_elem,)
    assert result.material_volumes.shape == (2,)
    assert result.element_energy_per_material.shape == (2, n_elem)


def test_solve_multi_material_stiff_field_lower_compliance(bimaterial_smoke, two_materials):
    """Same total volume budget: all-stiff has lower compliance than all-soft."""
    config, mesh = bimaterial_smoke
    n_elem = mesh.elements.shape[0]
    soft_only = np.array([np.full(n_elem, 0.5), np.zeros(n_elem)])
    stiff_only = np.array([np.zeros(n_elem), np.full(n_elem, 0.5)])
    r_soft = solve_multi_material(config, mesh, soft_only, two_materials, e_min=1.0)
    r_stiff = solve_multi_material(config, mesh, stiff_only, two_materials, e_min=1.0)
    assert r_stiff.compliance < r_soft.compliance


def test_solve_multi_material_single_material_matches_linear_elastic(bimaterial_smoke):
    """With M=1 and uniform density 1.0, compliance must match
    solve_linear_elastic computed with the single material's E."""
    from dataclasses import replace

    config, mesh = bimaterial_smoke
    n_elem = mesh.elements.shape[0]
    only_material = [MaterialProperty(name="only", young_modulus=70_000.0, poisson_ratio=0.3, density=2.7)]
    # Multi-material with one material at full density
    densities = np.full((1, n_elem), 1.0)
    r_multi = solve_multi_material(config, mesh, densities, only_material, e_min=1.0)

    # Equivalent single-material via solve_linear_elastic
    new_mat = replace(config.material, young_modulus=only_material[0].young_modulus, poisson_ratio=0.3)
    config_eq = replace(config, material=new_mat)
    eq_densities = np.full(n_elem, 1.0)
    r_eq = solve_linear_elastic(config_eq, mesh, eq_densities)
    # Multi-material uses SIMP scaling E_eff = E_min + ρ^p (E - E_min);
    # at ρ=1 and E_min=1 → E_eff = E. Should match linear elastic within
    # numerical tolerance (different assembly paths, same physics).
    rel = abs(r_multi.compliance - r_eq.compliance) / r_eq.compliance
    assert rel < 0.01, f"single-material multi != single, rel={rel:.4f}"


def test_solve_multi_material_rejects_count_mismatch(bimaterial_smoke, two_materials):
    config, mesh = bimaterial_smoke
    bad = np.zeros((3, mesh.elements.shape[0]))  # M=3 vs 2 materials
    with pytest.raises(SolverError, match="multi_material_count_mismatch"):
        solve_multi_material(config, mesh, bad, two_materials)


def test_solve_multi_material_rejects_density_mismatch(bimaterial_smoke, two_materials):
    config, mesh = bimaterial_smoke
    bad = np.zeros((2, mesh.elements.shape[0] + 1))
    with pytest.raises(SolverError, match="density_count_mismatch"):
        solve_multi_material(config, mesh, bad, two_materials)


# ---------------------------------------------------------------------------
# SIMP main loop
# ---------------------------------------------------------------------------


def test_run_multi_material_simp_smoke(bimaterial_smoke, two_materials):
    config, mesh = bimaterial_smoke
    result = run_multi_material_simp(config, mesh, two_materials, volume_fractions=[0.2, 0.2])
    assert result.densities_per_material.shape == (2, mesh.elements.shape[0])
    # Bounds
    assert (result.densities_per_material >= config.optimization.min_density - 1e-12).all()
    assert (result.densities_per_material <= 1.0 + 1e-12).all()
    assert len(result.metrics) >= 1
    assert result.material_names == ["soft", "stiff"]


def test_run_multi_material_simp_volume_constraints_respected(bimaterial_smoke, two_materials):
    config, mesh = bimaterial_smoke
    result = run_multi_material_simp(config, mesh, two_materials, volume_fractions=[0.2, 0.3])
    vol = result.final_result.material_volumes
    assert vol[0] <= 0.2 + 0.10
    assert vol[1] <= 0.3 + 0.10


def test_run_multi_material_simp_rejects_volume_count_mismatch(bimaterial_smoke, two_materials):
    config, mesh = bimaterial_smoke
    with pytest.raises(SolverError, match="volume_fractions_length_mismatch"):
        run_multi_material_simp(config, mesh, two_materials, volume_fractions=[0.5])


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


def test_property_ordered_simp_densities_in_bounds():
    """For random RNG seed, all per-material densities ∈ [min_density, 1]."""
    config = load_benchmark("bimaterial_beam", preset="smoke")
    mesh = create_structured_mesh(config)
    materials = [
        MaterialProperty(name="A", young_modulus=10_000.0, poisson_ratio=0.3, density=1.0),
        MaterialProperty(name="B", young_modulus=50_000.0, poisson_ratio=0.3, density=2.0),
        MaterialProperty(name="C", young_modulus=200_000.0, poisson_ratio=0.3, density=4.0),
    ]
    result = run_multi_material_simp(config, mesh, materials, volume_fractions=[0.1, 0.1, 0.1])
    assert (result.densities_per_material >= config.optimization.min_density - 1e-12).all()
    assert (result.densities_per_material <= 1.0 + 1e-12).all()


def test_property_ordered_simp_higher_volume_higher_compliance_reduction():
    """Giving more volume budget to the stiff material should produce
    lower (better) compliance."""
    config = load_benchmark("bimaterial_beam", preset="smoke")
    mesh = create_structured_mesh(config)
    soft = MaterialProperty(name="soft", young_modulus=10_000.0, poisson_ratio=0.3, density=1.0)
    stiff = MaterialProperty(name="stiff", young_modulus=200_000.0, poisson_ratio=0.3, density=3.0)

    r_more_stiff = run_multi_material_simp(config, mesh, [soft, stiff], volume_fractions=[0.1, 0.4])
    r_less_stiff = run_multi_material_simp(config, mesh, [soft, stiff], volume_fractions=[0.4, 0.1])
    assert r_more_stiff.final_result.compliance < r_less_stiff.final_result.compliance
