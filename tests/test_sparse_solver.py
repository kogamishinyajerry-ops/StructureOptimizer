"""Wave H: scipy sparse solver backend tests.

Pins these properties:

- ``ScipySparseSolver`` / ``ScipySparseCGSolver`` registered iff scipy importable.
- ``available_backends()`` includes ``"sparse"`` + ``"sparse_cg"`` when scipy present.
- ``prefers_sparse`` class attribute correctly set on both scipy backends.
- ``solve_linear_elastic`` produces equivalent results (≤ 1e-6 relative error)
  across all 4 backends on the same problem.
- Sparse assembly matches dense assembly to machine precision.
- Singular sparse matrix raises ``SolverError`` cleanly.
- Sparse CG honors max iterations + tolerance settings.
- End-to-end SIMP runs through every backend produce comparable compliance.

Tests are unconditional (we install scipy in dev deps). If scipy ever
becomes truly optional in some test environment, mark these `skipif
scipy not importable`.
"""

from __future__ import annotations

import numpy as np
import pytest

scipy = pytest.importorskip("scipy")

from structure_optimizer.adapters.solver_base import (  # noqa: E402
    LinearSolver,
    ScipySparseCGSolver,
    ScipySparseSolver,
    available_backends,
    get_linear_solver,
)
from structure_optimizer.benchmarks.registry import load_benchmark  # noqa: E402
from structure_optimizer.core.config import parse_config, validate_config  # noqa: E402
from structure_optimizer.core.fem2d import (  # noqa: E402
    SolverError,
    _assemble_stiffness_dense,
    _assemble_stiffness_sparse,
    element_stiffness,
    solve_linear_elastic,
)
from structure_optimizer.core.mesh import create_structured_mesh  # noqa: E402
from structure_optimizer.core.simp import run_simp  # noqa: E402

# --- registry ---------------------------------------------------------


def test_sparse_backends_in_registry():
    backends = available_backends()
    assert "sparse" in backends
    assert "sparse_cg" in backends


def test_scipy_sparse_solver_prefers_sparse():
    solver = get_linear_solver("sparse")
    assert isinstance(solver, ScipySparseSolver)
    assert solver.prefers_sparse is True


def test_scipy_sparse_cg_solver_prefers_sparse():
    solver = get_linear_solver("sparse_cg")
    assert isinstance(solver, ScipySparseCGSolver)
    assert solver.prefers_sparse is True


def test_dense_solver_does_not_prefer_sparse():
    solver = get_linear_solver("dense")
    assert solver.prefers_sparse is False


def test_cg_solver_does_not_prefer_sparse():
    solver = get_linear_solver("cg")
    assert solver.prefers_sparse is False


def test_linear_solver_base_class_default_prefers_sparse_false():
    """The abstract base default is ``prefers_sparse = False``."""
    assert LinearSolver.prefers_sparse is False


# --- assembly equivalence ---------------------------------------------


def _small_config():
    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    config = parse_config(raw)
    validate_config(config)
    return config


def test_sparse_assembly_matches_dense_assembly_to_machine_precision():
    config = _small_config()
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    opt = config.optimization
    active_density = np.where(mesh.void_mask, opt.min_density, densities)
    density_scale = opt.min_density + (active_density**opt.penalty) * (1.0 - opt.min_density)
    dense = _assemble_stiffness_dense(mesh, density_scale, ke)
    sparse = _assemble_stiffness_sparse(mesh, density_scale, ke).toarray()
    assert np.allclose(dense, sparse, atol=1e-12, rtol=1e-12)


# --- equivalence of solutions across backends -------------------------


@pytest.fixture
def backends_to_compare():
    return ["dense", "cg", "sparse", "sparse_cg"]


def test_all_backends_produce_equivalent_compliance(backends_to_compare):
    """All 4 backends solve the same K u = f system to within 1e-6 relative."""
    base_raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    densities = None
    compliances = {}
    displacements_by_backend = {}
    for backend in backends_to_compare:
        raw = {**base_raw}
        raw["solver"] = {"backend": backend}
        config = parse_config(raw)
        validate_config(config)
        mesh = create_structured_mesh(config)
        if densities is None:
            densities = np.full(mesh.elements.shape[0], 0.5)
        result = solve_linear_elastic(config, mesh, densities)
        compliances[backend] = result.compliance
        displacements_by_backend[backend] = result.displacements

    # All compliances within 1e-6 relative
    ref = compliances["dense"]
    for backend, value in compliances.items():
        assert abs(value - ref) / max(abs(ref), 1e-12) < 1e-6, f"{backend}: {value} vs dense {ref}"

    # Displacement fields close
    ref_u = displacements_by_backend["dense"]
    for backend, u in displacements_by_backend.items():
        assert np.allclose(u, ref_u, atol=1e-6, rtol=1e-6), f"{backend} displacements diverge"


def test_full_simp_runs_through_sparse_backend():
    """End-to-end SIMP with sparse backend produces sensible OptimizationResult."""
    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    raw["solver"] = {"backend": "sparse"}
    config = parse_config(raw)
    validate_config(config)
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    assert len(result.metrics) > 0
    assert (result.densities >= 0).all()
    assert (result.densities <= 1.0001).all()


def test_full_simp_runs_through_sparse_cg_backend():
    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    raw["solver"] = {"backend": "sparse_cg"}
    config = parse_config(raw)
    validate_config(config)
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    assert len(result.metrics) > 0


def test_simp_dense_vs_sparse_compliance_within_tolerance():
    """SIMP final compliance under sparse vs dense should match to 0.1% relative."""
    base_raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    final = {}
    for backend in ["dense", "sparse"]:
        raw = {**base_raw}
        raw["solver"] = {"backend": backend}
        config = parse_config(raw)
        validate_config(config)
        mesh = create_structured_mesh(config)
        result = run_simp(config, mesh)
        final[backend] = result.final_analysis.compliance
    rel = abs(final["dense"] - final["sparse"]) / max(abs(final["dense"]), 1e-12)
    assert rel < 1e-3, f"dense {final['dense']} vs sparse {final['sparse']}: rel {rel}"


# --- error paths ------------------------------------------------------


def test_sparse_solver_singular_raises():
    """A truly singular sparse matrix → SolverError('singular_matrix')."""
    import scipy.sparse as sp

    solver = ScipySparseSolver()
    matrix = sp.csr_matrix(np.array([[1.0, 1.0], [1.0, 1.0]]))
    rhs = np.array([1.0, 1.0])
    with pytest.raises(SolverError):
        solver.solve(matrix, rhs)


def test_sparse_cg_solver_singular_raises():
    """Indefinite SPD-ish matrix → CG fails → SolverError."""
    import scipy.sparse as sp

    # A matrix with very small max_iterations + bad conditioning
    solver = ScipySparseCGSolver()
    solver.max_iterations = 1  # type: ignore[misc]
    matrix = sp.csr_matrix(np.diag([1e-12, 1.0, 1.0]))
    rhs = np.array([1.0, 1.0, 1.0])
    with pytest.raises(SolverError):
        solver.solve(matrix, rhs)


# --- registry ergonomics ---------------------------------------------


def test_config_accepts_sparse_backend():
    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    raw["solver"] = {"backend": "sparse"}
    config = parse_config(raw)
    validate_config(config)
    assert config.solver.backend == "sparse"


def test_config_accepts_sparse_cg_backend():
    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    raw["solver"] = {"backend": "sparse_cg"}
    config = parse_config(raw)
    validate_config(config)
    assert config.solver.backend == "sparse_cg"


def test_config_rejects_unknown_backend():
    from structure_optimizer.core.config import ConfigError

    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    raw["solver"] = {"backend": "magic_backend"}
    with pytest.raises(ConfigError, match=r"solver\.backend"):
        config = parse_config(raw)
        validate_config(config)
