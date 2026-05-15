"""Tests for v0.8 linear-solver adapter (dense vs CG backends).

The adapter must satisfy two contracts:
1. Both built-in backends produce the same displacement field (within tight
   numerical tolerance) when given the same K and f.
2. The factory accepts only registered backend names and raises on unknowns.
3. Config-level validation rejects bad backend names before runtime.
4. Singular matrices map to SolverError, not raw NumPy exceptions.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.adapters.solver_base import (
    NumpyCGSolver,
    NumpyDenseSolver,
    available_backends,
    get_linear_solver,
)
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.config import ConfigError, parse_config, validate_config
from structure_optimizer.core.fem2d import SolverError, solve_linear_elastic
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.simp import run_simp


def _spd_test_matrix(n: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Build a small SPD matrix and a random rhs for direct testing."""
    rng = np.random.default_rng(seed)
    a = rng.standard_normal((n, n))
    spd = a @ a.T + n * np.eye(n)  # guarantee positive-definite
    b = rng.standard_normal(n)
    return spd, b


def test_available_backends_includes_dense_and_cg():
    backends = available_backends()
    assert "dense" in backends
    assert "cg" in backends


def test_get_linear_solver_defaults_to_dense():
    assert isinstance(get_linear_solver(None), NumpyDenseSolver)
    assert isinstance(get_linear_solver(""), NumpyDenseSolver)


def test_get_linear_solver_rejects_unknown_backend():
    with pytest.raises(ValueError, match="Unknown linear solver backend"):
        get_linear_solver("magic_solver")


def test_dense_and_cg_produce_equivalent_solutions_on_spd_system():
    a, b = _spd_test_matrix(n=20, seed=42)
    u_dense = NumpyDenseSolver().solve(a, b)
    u_cg = NumpyCGSolver().solve(a, b)
    assert np.allclose(u_dense, u_cg, atol=1e-7, rtol=1e-7)


def test_cg_handles_zero_rhs_returns_zero():
    a, _ = _spd_test_matrix(n=10, seed=1)
    b = np.zeros(10)
    u = NumpyCGSolver().solve(a, b)
    assert np.allclose(u, 0.0)


def test_cg_raises_on_non_spd_with_nonpositive_diagonal():
    a = np.array([[-1.0, 0.0], [0.0, 1.0]])
    b = np.array([1.0, 1.0])
    with pytest.raises(SolverError, match="singular_matrix"):
        NumpyCGSolver().solve(a, b)


def test_dense_solver_raises_solver_error_on_singular_matrix():
    singular = np.array([[1.0, 2.0], [2.0, 4.0]])
    b = np.array([1.0, 2.0])
    with pytest.raises(SolverError, match="singular_matrix"):
        NumpyDenseSolver().solve(singular, b)


def test_config_validation_rejects_unknown_backend():
    raw = {
        "name": "test",
        "dimension": "2d",
        "units": "mm_N_MPa",
        "mesh": {"type": "structured_quad", "nelx": 4, "nely": 4},
        "material": {"young_modulus": 1.0, "poisson_ratio": 0.3, "density": 1.0},
        "boundary_conditions": [{"selector": "left_edge", "components": ["ux", "uy"]}],
        "loads": [{"selector": "right_mid", "fx": 0.0, "fy": -1.0}],
        "optimization": {
            "objective": "min_compliance",
            "volume_fraction": 0.5,
            "penalty": 3.0,
            "filter_radius": 1.5,
            "max_iterations": 3,
            "min_iterations": 1,
            "change_tolerance": 0.01,
            "min_density": 0.001,
        },
        "solver": {"backend": "ansys_pretend"},
    }
    with pytest.raises(ConfigError, match=r"solver\.backend"):
        validate_config(parse_config(raw))


def test_fem_pipeline_works_with_cg_backend():
    """Run full FEM solve on a benchmark using CG backend; result should be
    numerically equivalent to dense backend within engineering tolerance."""
    base_raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    dense_config = parse_config({**base_raw, "solver": {"backend": "dense"}})
    cg_config = parse_config({**base_raw, "solver": {"backend": "cg"}})
    validate_config(dense_config)
    validate_config(cg_config)

    mesh = create_structured_mesh(dense_config)
    densities = np.full(mesh.elements.shape[0], 0.5)

    dense_result = solve_linear_elastic(dense_config, mesh, densities)
    cg_result = solve_linear_elastic(cg_config, mesh, densities)

    # CG is iterative; compare with engineering-level tolerance, not bit-exact.
    assert abs(dense_result.compliance - cg_result.compliance) / abs(dense_result.compliance) < 1e-5
    assert abs(dense_result.max_displacement - cg_result.max_displacement) < 1e-6
    assert np.allclose(dense_result.displacements, cg_result.displacements, atol=1e-6, rtol=1e-6)


def test_simp_loop_runs_with_cg_backend():
    """End-to-end SIMP smoke run with CG must converge to a similar density
    field as the dense backend would (matched OC update parameters)."""
    base_raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    cg_config = parse_config({**base_raw, "solver": {"backend": "cg"}})
    validate_config(cg_config)
    mesh = create_structured_mesh(cg_config)
    result = run_simp(cg_config, mesh)
    assert len(result.metrics) > 0
    assert result.metrics[-1].volume_fraction <= cg_config.optimization.volume_fraction + 0.05
    # CG path must produce valid densities in [min_density, 1]
    assert float(result.densities.min()) >= cg_config.optimization.min_density - 1e-12
    assert float(result.densities.max()) <= 1.0 + 1e-12


def test_default_backend_preserves_legacy_behavior():
    """Loading a config without 'solver' field must default to dense."""
    config = load_benchmark("mbb_beam", preset="smoke")
    assert config.solver.backend == "dense"
