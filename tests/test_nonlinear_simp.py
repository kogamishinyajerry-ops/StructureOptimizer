"""Wave AA: nonlinear SIMP driver tests."""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.nonlinear_simp import run_nonlinear_simp


@pytest.fixture
def nonlinear_cantilever_smoke():
    config = load_benchmark("nonlinear_cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    return config, mesh


def test_nonlinear_simp_smoke_runs(nonlinear_cantilever_smoke):
    config, mesh = nonlinear_cantilever_smoke
    result = run_nonlinear_simp(config, mesh, n_load_steps=2)
    assert result.densities.shape == (mesh.elements.shape[0],)
    assert (result.densities >= config.optimization.min_density - 1e-9).all()
    assert (result.densities <= 1.0 + 1e-9).all()
    assert len(result.metrics) >= 1


def test_nonlinear_simp_volume_constraint_eventually_satisfied(nonlinear_cantilever_smoke):
    config, mesh = nonlinear_cantilever_smoke
    result = run_nonlinear_simp(config, mesh, n_load_steps=2)
    final_vol = result.metrics[-1].volume_fraction
    assert final_vol <= config.optimization.volume_fraction + 0.10


def test_nonlinear_simp_emits_newton_iteration_counts(nonlinear_cantilever_smoke):
    config, mesh = nonlinear_cantilever_smoke
    result = run_nonlinear_simp(config, mesh, n_load_steps=2)
    # Each iteration ran at least 1 Newton iter
    assert all(m.newton_iters >= 1 for m in result.metrics)


def test_nonlinear_simp_metrics_compliance_finite(nonlinear_cantilever_smoke):
    config, mesh = nonlinear_cantilever_smoke
    result = run_nonlinear_simp(config, mesh, n_load_steps=2)
    for m in result.metrics:
        assert np.isfinite(m.nonlinear_compliance)
        assert m.nonlinear_compliance >= 0  # compliance = f · u and f, u align


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


def test_property_nonlinear_simp_densities_in_bounds(nonlinear_cantilever_smoke):
    config, mesh = nonlinear_cantilever_smoke
    result = run_nonlinear_simp(config, mesh, n_load_steps=2)
    assert (result.densities >= config.optimization.min_density - 1e-12).all()
    assert (result.densities <= 1.0 + 1e-12).all()
