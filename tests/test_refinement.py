"""Wave V tests for auto-refinement loop (D010 close)."""

from __future__ import annotations

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.refinement import (
    RefinementResult,
    _interpolate_densities_to_finer_mesh,
    _refine_config,
    auto_refine_until_converged,
)


def test_refine_config_doubles_mesh():
    """factor=2 → nelx, nely both double; filter_radius scales."""
    config = load_benchmark("cantilever", preset="smoke")
    refined = _refine_config(config, factor=2)
    assert refined.mesh.nelx == config.mesh.nelx * 2
    assert refined.mesh.nely == config.mesh.nely * 2
    assert refined.optimization.filter_radius == config.optimization.filter_radius * 2


def test_interpolate_densities_factor_2():
    """2× refinement: each coarse cell → 4 fine cells with the same value."""
    coarse = np.array([0.1, 0.9, 0.5, 0.7])  # 2×2 grid
    fine = _interpolate_densities_to_finer_mesh(coarse, coarse_nelx=2, coarse_nely=2, fine_nelx=4, fine_nely=4)
    # The 2×2 grid corresponds to nely=2 rows of nelx=2:
    # row 0: [0.1, 0.9]  row 1: [0.5, 0.7]
    # After 2× refinement: 4×4 fine. Each coarse cell becomes 2×2 fine.
    fine2d = fine.reshape((4, 4))
    # Top-left 2×2 should be coarse[0,0] = 0.1
    assert np.allclose(fine2d[:2, :2], 0.1)
    assert np.allclose(fine2d[:2, 2:], 0.9)
    assert np.allclose(fine2d[2:, :2], 0.5)
    assert np.allclose(fine2d[2:, 2:], 0.7)


def test_auto_refine_returns_result_with_levels():
    """The driver should run at base resolution at minimum."""
    config = load_benchmark("cantilever", preset="smoke")
    result = auto_refine_until_converged(config, max_levels=1)
    assert isinstance(result, RefinementResult)
    assert len(result.levels) == 1
    assert result.levels[0].nelx == config.mesh.nelx
    assert result.levels[0].nely == config.mesh.nely


def test_auto_refine_multiple_levels_records_history():
    """With max_levels=2, the history should include both coarse + refined."""
    config = load_benchmark("cantilever", preset="smoke")
    result = auto_refine_until_converged(config, max_levels=2)
    assert len(result.levels) <= 2  # may stop early on compliance_converged
    assert len(result.levels) >= 1
    # Each level records nelx/nely consistent with refinement factor
    if len(result.levels) >= 2:
        assert result.levels[1].nelx == result.levels[0].nelx * 2


def test_auto_refine_stop_reason_either_converged_or_max():
    """stop_reason must be one of the known values."""
    config = load_benchmark("cantilever", preset="smoke")
    result = auto_refine_until_converged(config, max_levels=1)
    assert result.stop_reason in {"compliance_converged", "max_levels"}


def test_auto_refine_compliance_tolerance_can_force_early_stop():
    """A huge tolerance → stop after 2 levels (compliance always within tol)."""
    config = load_benchmark("cantilever", preset="smoke")
    result = auto_refine_until_converged(config, max_levels=3, compliance_tolerance=10.0)
    # Compliance change is at most ~100% on smoke meshes; tol=10 (1000% rel)
    # guarantees stop after level 1 comparison
    assert result.stop_reason == "compliance_converged"
    assert len(result.levels) == 2


def test_auto_refine_convergence_history_matches_levels():
    """convergence_history length == levels length."""
    config = load_benchmark("cantilever", preset="smoke")
    result = auto_refine_until_converged(config, max_levels=2)
    assert len(result.convergence_history) == len(result.levels)
    # Compliance values must be positive
    for c in result.convergence_history:
        assert c > 0
