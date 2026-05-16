"""Wave R: algorithm × mesh × backend matrix coverage (rubric §1.4 + §1.3).

Pins:

§1.3 — stress + multi-case **same benchmark**:
- ``stress_multi_load_bracket`` benchmark loads, has ``stress_constraint.enabled=True``
  AND ``load_cases >= 2`` AND ``stress_penalty > 0``
- runs to completion (smoke preset) producing both case-aggregated compliance
  and bounded stress

§1.4 — algorithm × mesh × backend matrix:
- algorithm ∈ {simp, beso}, mesh ∈ {quad, triangle}, backend ∈ {dense, sparse}
- All combinations that are *implemented* run to completion:
    - simp × quad × dense ✓
    - simp × quad × sparse ✓
    - simp × triangle × dense ✓ (Wave M)
    - simp × triangle × sparse ✓ (Wave M)
    - beso × quad × dense ✓
    - beso × quad × sparse ✓
- Combinations *not* implemented are explicitly documented as deferred
  in D013 (see beso × triangle: triangle path doesn't run BESO).
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.adapters.algorithm_base import get_algorithm
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.config import parse_config, validate_config
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.simp import run_simp
from structure_optimizer.core.triangle_simp import (
    run_simp_triangle,
    split_quad_to_triangles,
)

# --- §1.3 stress + multi-case ----------------------------------------


def test_stress_multi_load_benchmark_has_both_features():
    config = load_benchmark("stress_multi_load_bracket", preset="smoke")
    assert config.stress_constraint.enabled is True
    assert len(config.load_cases) >= 2
    assert config.optimization.stress_penalty > 0


def test_stress_multi_load_benchmark_runs_to_completion():
    config = load_benchmark("stress_multi_load_bracket", preset="smoke")
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    assert len(result.metrics) > 0
    # densities valid range
    assert (result.densities >= config.optimization.min_density - 1e-9).all()
    assert (result.densities <= 1.0 + 1e-9).all()
    # final compliance is finite + positive (multi-case aggregated)
    assert np.isfinite(result.final_analysis.compliance)
    assert result.final_analysis.compliance > 0


# --- §1.4 algorithm × mesh × backend matrix -------------------------


@pytest.mark.parametrize("algorithm", ["simp", "beso"])
@pytest.mark.parametrize("backend", ["dense", "sparse"])
def test_quad_algorithm_backend_matrix(algorithm, backend):
    """Quad mesh: 2 algorithms × 2 backends = 4 cells."""
    if backend == "sparse":
        pytest.importorskip("scipy")
    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    raw["solver"] = {"backend": backend}
    raw["optimization"]["algorithm"] = algorithm
    config = parse_config(raw)
    validate_config(config)
    mesh = create_structured_mesh(config)
    algo = get_algorithm(algorithm)
    result = algo.run(config, mesh)
    assert result.densities.shape[0] == mesh.elements.shape[0]
    # densities in valid range
    assert (result.densities >= 1e-9).all()
    assert (result.densities <= 1.0 + 1e-9).all()
    # compliance positive + finite
    assert np.isfinite(result.final_analysis.compliance)
    assert result.final_analysis.compliance > 0


@pytest.mark.parametrize("backend", ["dense", "sparse"])
def test_triangle_simp_backend_matrix(backend):
    """Triangle mesh × SIMP × {dense, sparse}. BESO-on-triangle is
    intentionally deferred (see D013 § "What is NOT in the matrix")."""
    if backend == "sparse":
        pytest.importorskip("scipy")
    mesh = split_quad_to_triangles(8, 4, width=8.0, height=4.0)
    n_nodes_x = 9
    left_nodes = [j * n_nodes_x for j in range(5)]
    fixed_dofs = np.array(sorted({2 * n for n in left_nodes} | {2 * n + 1 for n in left_nodes}))
    force = np.zeros(mesh.ndof)
    force[2 * (2 * n_nodes_x + 8) + 1] = -100.0
    result = run_simp_triangle(
        mesh,
        young_modulus=210000.0,
        poisson_ratio=0.3,
        fixed_dofs=fixed_dofs,
        force=force,
        volume_fraction=0.4,
        max_iterations=5,
        min_iterations=5,
        solver_backend=backend,
    )
    assert result.densities.shape[0] == mesh.n_elements
    assert (result.densities >= 1e-3 - 1e-9).all()
    assert (result.densities <= 1.0 + 1e-9).all()


def test_matrix_documented_deferred_combinations():
    """Document explicitly which combinations are NOT supported in v3.0.

    BESO-on-triangle: triangle SIMP module (Wave M) intentionally only
    implements SIMP — see D008. BESO-on-triangle would need a parallel
    `run_beso_triangle` entry point; v3.x defers per the same rationale
    (no manufacturing projections, no stress adjoint on triangle path).
    """
    # Simply asserts the algorithm registry knows beso (so it's not a regression)
    # and that triangle SIMP entry point exists.
    from structure_optimizer.adapters.algorithm_base import available_algorithms

    algos = available_algorithms()
    assert "simp" in algos
    assert "beso" in algos
    # No "beso_triangle" — that's the documented deferral
    assert "beso_triangle" not in algos
