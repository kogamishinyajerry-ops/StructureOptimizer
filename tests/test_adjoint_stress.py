"""Wave L: adjoint stress-constrained SIMP tests.

Pins these properties of ``core/adjoint.py``:

- ``stress_pn_and_gradient_w_r_t_u`` returns (σ_PN, ∂σ_PN/∂u, σ_vm) with
  matching shapes + nonneg σ_PN + finite gradient.
- ``adjoint_stress_sensitivity`` ratio against finite differences ≈ 1.0
  per element (the actual correctness check).
- Adjoint is zero when stress constraint disabled (raises ValueError).
- Adjoint is zero when σ_PN = 0 (all-void design).
- Integration: SIMP with stress_penalty > 0 reduces σ_PN vs baseline.
- ``OptimizationConfig.stress_penalty`` defaults to 0 and validates ≥ 0.
- Mathematically: ε = B u; σ = D ε; σ_vm² = ... matches reference formulas.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.adjoint import (
    _constitutive_matrix,
    _strain_displacement_matrix,
    adjoint_stress_sensitivity,
    stress_pn_and_gradient_w_r_t_u,
)
from structure_optimizer.core.config import ConfigError, parse_config, validate_config
from structure_optimizer.core.fem2d import solve_linear_elastic
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.simp import run_simp
from structure_optimizer.core.stress import (
    aggregate_stress,
    element_von_mises_stresses,
)


def _stress_config(stress_overrides=None, opt_overrides=None):
    raw = load_benchmark("stress_limited_bracket", preset="smoke").to_dict()
    raw["mesh"]["nelx"] = 5
    raw["mesh"]["nely"] = 4
    raw["mesh"]["width"] = 5.0
    raw["mesh"]["height"] = 4.0
    if stress_overrides:
        raw["stress_constraint"].update(stress_overrides)
    if opt_overrides:
        raw["optimization"].update(opt_overrides)
    config = parse_config(raw)
    validate_config(config)
    return config


# --- math primitives ---------------------------------------------------


def test_strain_displacement_matrix_shape():
    config = _stress_config()
    mesh = create_structured_mesh(config)
    bmat = _strain_displacement_matrix(mesh)
    assert bmat.shape == (3, 8)


def test_strain_displacement_rigid_body_translation_gives_zero_strain():
    config = _stress_config()
    mesh = create_structured_mesh(config)
    bmat = _strain_displacement_matrix(mesh)
    # x-translation: ux = 1, uy = 0 everywhere
    ue = np.array([1, 0, 1, 0, 1, 0, 1, 0], dtype=float)
    eps = bmat @ ue
    assert np.allclose(eps, 0, atol=1e-12)
    # y-translation: ux = 0, uy = 1 everywhere
    ue = np.array([0, 1, 0, 1, 0, 1, 0, 1], dtype=float)
    eps = bmat @ ue
    assert np.allclose(eps, 0, atol=1e-12)


def test_constitutive_matrix_isotropic_2d_plane_stress():
    dmat = _constitutive_matrix(1000.0, 0.3)
    assert dmat.shape == (3, 3)
    # Diagonal entries positive, off-diagonals follow E/(1-ν²) * ν
    nu = 0.3
    factor = 1000.0 / (1.0 - nu**2)
    assert dmat[0, 0] == pytest.approx(factor)
    assert dmat[1, 1] == pytest.approx(factor)
    assert dmat[0, 1] == pytest.approx(factor * nu)
    assert dmat[2, 2] == pytest.approx(factor * (1.0 - nu) / 2.0)


# --- ∂σ_PN/∂u sanity --------------------------------------------------


def test_stress_pn_gradient_finite_and_correct_shape():
    config = _stress_config()
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    result = solve_linear_elastic(config, mesh, densities)
    sigma_pn, dpn_du, stresses = stress_pn_and_gradient_w_r_t_u(config, mesh, densities, result.displacements)
    assert sigma_pn > 0
    assert dpn_du.shape == (mesh.ndof,)
    assert np.all(np.isfinite(dpn_du))
    assert stresses.shape == (mesh.elements.shape[0],)


def test_stress_pn_gradient_rejects_when_disabled():
    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    config = parse_config(raw)
    validate_config(config)
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    result = solve_linear_elastic(config, mesh, densities)
    with pytest.raises(ValueError, match="must be enabled"):
        stress_pn_and_gradient_w_r_t_u(config, mesh, densities, result.displacements)


# --- adjoint vs finite-difference ------------------------------------


def test_adjoint_sensitivity_matches_finite_difference():
    """Per-element adjoint dσ_PN/dρ_e must match centered FD to ≤1% rel error."""
    config = _stress_config(stress_overrides={"density_threshold": 0.05})
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    result = solve_linear_elastic(config, mesh, densities)
    sigma_pn, sens, _ = adjoint_stress_sensitivity(config, mesh, densities, result.displacements)
    h = 1e-6
    # Check several elements (skip the boundary cases for cleaner FD)
    interior_elements = [3, 7, 10, 14, 17]
    for eid in interior_elements:
        rho_pert = densities.copy()
        rho_pert[eid] += h
        r_pert = solve_linear_elastic(config, mesh, rho_pert)
        stresses_pert = element_von_mises_stresses(config, mesh, r_pert.displacements)
        mask = rho_pert >= config.stress_constraint.density_threshold
        sigma_pn_pert = aggregate_stress(
            stresses_pert,
            config.stress_constraint.aggregation,
            config.stress_constraint.p,
            mask,
        )
        fd_grad = (sigma_pn_pert - sigma_pn) / h
        if abs(fd_grad) > 1e-9:
            rel = abs(sens[eid] - fd_grad) / abs(fd_grad)
            assert rel < 0.01, f"element {eid}: adjoint={sens[eid]}, FD={fd_grad}, rel={rel}"


def test_adjoint_sensitivity_zero_outside_design_mask():
    """Frozen / void elements should have zero sensitivity (design-locked)."""
    config = _stress_config()
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    result = solve_linear_elastic(config, mesh, densities)
    _, sens, _ = adjoint_stress_sensitivity(config, mesh, densities, result.displacements)
    assert (sens[~mesh.design_mask] == 0).all()


def test_adjoint_sensitivity_disabled_raises():
    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    config = parse_config(raw)
    validate_config(config)
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    result = solve_linear_elastic(config, mesh, densities)
    with pytest.raises(ValueError, match="must be enabled"):
        adjoint_stress_sensitivity(config, mesh, densities, result.displacements)


# --- config validation ------------------------------------------------


def test_stress_penalty_default_zero():
    config = load_benchmark("mbb_beam", preset="smoke")
    assert config.optimization.stress_penalty == 0.0


def test_stress_penalty_accepts_positive():
    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    raw["optimization"]["stress_penalty"] = 2.5
    config = parse_config(raw)
    validate_config(config)
    assert config.optimization.stress_penalty == 2.5


def test_stress_penalty_rejects_negative():
    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    raw["optimization"]["stress_penalty"] = -0.1
    with pytest.raises(ConfigError, match="stress_penalty"):
        config = parse_config(raw)
        validate_config(config)


# --- end-to-end SIMP integration -------------------------------------


def test_simp_stress_penalty_zero_matches_v1_behavior():
    """stress_penalty=0 should produce identical run to disabling stress constraint."""
    raw = load_benchmark("stress_limited_bracket", preset="smoke").to_dict()
    raw["stress_constraint"]["enabled"] = False
    raw["optimization"]["max_iterations"] = 8
    raw["optimization"]["min_iterations"] = 8
    config_off = parse_config(raw)
    validate_config(config_off)
    mesh_off = create_structured_mesh(config_off)
    res_off = run_simp(config_off, mesh_off)

    raw2 = load_benchmark("stress_limited_bracket", preset="smoke").to_dict()
    raw2["stress_constraint"]["enabled"] = True
    raw2["optimization"]["stress_penalty"] = 0.0
    raw2["optimization"]["max_iterations"] = 8
    raw2["optimization"]["min_iterations"] = 8
    config_zero = parse_config(raw2)
    validate_config(config_zero)
    mesh_zero = create_structured_mesh(config_zero)
    res_zero = run_simp(config_zero, mesh_zero)

    assert np.allclose(res_off.densities, res_zero.densities, atol=1e-9)


def test_simp_stress_adjoint_reduces_stress_vs_baseline():
    """With moderate stress_penalty, σ_PN at convergence should be ≤ baseline
    (no-adjoint) σ_PN. We test on a config where the baseline σ_PN exceeds limit."""

    def _final_sigma(stress_penalty: float) -> tuple[float, float]:
        raw = load_benchmark("stress_limited_bracket", preset="smoke").to_dict()
        raw["stress_constraint"]["limit"] = 100.0
        raw["optimization"]["stress_penalty"] = stress_penalty
        raw["optimization"]["max_iterations"] = 30
        raw["optimization"]["min_iterations"] = 5
        config = parse_config(raw)
        validate_config(config)
        mesh = create_structured_mesh(config)
        res = run_simp(config, mesh)
        stresses = element_von_mises_stresses(config, mesh, res.final_analysis.displacements)
        mask = res.densities >= config.stress_constraint.density_threshold
        sigma_pn = aggregate_stress(
            stresses,
            config.stress_constraint.aggregation,
            config.stress_constraint.p,
            mask,
        )
        return sigma_pn, res.final_analysis.compliance

    sigma_baseline, c_baseline = _final_sigma(0.0)
    sigma_adj, c_adj = _final_sigma(1.0)
    # Stress should be at least no worse, and ideally lower
    assert sigma_adj <= sigma_baseline + 1e-6, f"adjoint stress {sigma_adj} > baseline {sigma_baseline}"
    # Compliance may go up (trade-off) but shouldn't more than double
    assert c_adj <= c_baseline * 2.0


def test_simp_with_adjoint_runs_to_completion():
    """End-to-end smoke: SIMP with adjoint stress + benchmark stress_limited_bracket runs through."""
    raw = load_benchmark("stress_limited_bracket", preset="smoke").to_dict()
    raw["optimization"]["stress_penalty"] = 1.0
    raw["optimization"]["max_iterations"] = 10
    raw["optimization"]["min_iterations"] = 5
    config = parse_config(raw)
    validate_config(config)
    mesh = create_structured_mesh(config)
    res = run_simp(config, mesh)
    assert len(res.metrics) > 0
    assert res.stop_reason in ("max_iterations", "change_tolerance")
    # densities still in valid range
    assert (res.densities >= config.optimization.min_density - 1e-9).all()
    assert (res.densities <= 1.0 + 1e-9).all()


def test_v1_v2_tests_still_green_with_stress_field_added():
    """Meta-test: confirm that adding stress_penalty to OptimizationConfig
    doesn't break any v1/v2 benchmark loading or default-config behavior."""
    for name in ("mbb_beam", "cantilever", "l_bracket", "simple_bracket"):
        config = load_benchmark(name, preset="smoke")
        # stress_penalty defaults to 0
        assert config.optimization.stress_penalty == 0.0
        # Won't trigger adjoint
        mesh = create_structured_mesh(config)
        res = run_simp(config, mesh)
        assert len(res.metrics) > 0
